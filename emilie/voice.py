"""Voice output: the agent's reply is spoken by a local Voicebox server (cloned voice).

Flow:  reply finished -> <say> line (or whole reply) -> POST /generate -> wait -> GET /audio -> play.
Everything runs in a background thread, so the terminal never blocks. If the server is down, Emilie
keeps working silently (one note is shown).

Settings (~/.emilie/settings.json): voice, voice_mode (say|full), voice_lang, voice_profile,
voice_url, voice_dir, voice_engine, voice_size.
"""
from . import paths
import io
import itertools
import json
import math
import os
import queue
import re
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

from .i18n import t as tr_
from . import effort

LANG_NAMES = {"ja": "Japanese", "en": "English", "ms": "Malay", "ko": "Korean", "zh": "Chinese"}
def _detach() -> dict:
    """Popen kwargs that detach a child from our console/session (POSIX and Windows)."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}


SAY_RE = re.compile(r"<say>(.*?)</say>", re.S | re.I)
CODE_BLOCK = re.compile(r"```.*?```", re.S)
STORY_RE = re.compile(
    r"dongeng|cerita(?:kan)?\s+(?:pengantar\s+)?(?:tidur|sebelum\s+tidur|malam)|pengantar\s+tidur|"
    r"bedtime\s+stor|fairy\s*tale|story\s+(?:before|for)\s+(?:bed|sleep)|sleep\s+story|"
    r"読み聞かせ|おとぎ話|昔話|寝る前", re.I)
LOG = paths.HOME_DIR / "voicebox.log"


def _cfg(key: str, default):
    return effort.load_settings().get(key, default)


def clean_for_speech(text: str, limit: int = 600) -> str:
    """Remove what should not be read aloud: code, urls, markdown, tags, emoji-like symbols."""
    t = CODE_BLOCK.sub(" ", text)
    t = re.sub(r"`[^`]*`", " ", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"</?say>", " ", t, flags=re.I)
    # roleplay actions / stage directions are shown but never spoken: *hugs you*, _sighs_, (laughs), [smiles]
    t = re.sub(r"(?<!\*)\*(?!\*)[^*\n]+\*(?!\*)", " ", t)          # *action* (a single pair; **bold** is kept)
    t = re.sub(r"(?<!\w)_+[^_\n]+_+(?!\w)", " ", t)
    t = re.sub(r"\([^()\n]*\)", " ", t)
    t = re.sub(r"\[[^\[\]\n]*\]", " ", t)
    t = re.sub(r"[#*_>|~\[\]{}<>=]+", " ", t)
    t = re.sub(r"[\U00010000-\U0010ffff☀-➿]", " ", t)        # emoji / dingbats
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit]


LATE_S = 75.0        # audio that turns up this long after its words were already shown is dropped, not read out of sync
SENT_MAX = 190       # a block longer than this is spoken as several short clips (one long clip can take minutes to generate)
FIRST_CHUNK = 160    # the first clip of a reply is kept short so the voice starts sooner; the later ones are generated while it plays
CHUNK = 450          # characters per generated voice clip: one clip per reply when it fits, a few for a long one


def _split_speech(text: str, size: int = SENT_MAX) -> list[str]:
    """Cut a long text at sentence ends into pieces of about `size` characters (never inside a sentence if it can be helped)."""
    if len(text) <= size:
        return [text]
    sents = re.split(r"(?<=[.!?…~。！？])\s+", text)
    out, cur = [], ""
    for sent in sents:
        while len(sent) > size:                                   # one endless sentence: cut at a comma or a space
            k = max(sent.rfind(", ", 0, size), sent.rfind(" ", 0, size))
            k = k if k > size // 3 else size
            if cur:
                out.append(cur)
                cur = ""
            out.append(sent[:k].strip())
            sent = sent[k:].strip()
        if cur and len(cur) + 1 + len(sent) > size:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return [x for x in out if x]


def _duration(audio: bytes, text: str) -> float:
    try:
        with wave.open(io.BytesIO(audio)) as w:
            return max(0.5, w.getnframes() / float(w.getframerate()))
    except Exception:
        return max(1.0, len(text) / 14.0)


def _level_step(rate: int, frames: int) -> int:
    return max(1, round(rate * .05), (frames + 2399) // 2400)


def _visual_level(rms: float) -> float:
    return round(min(1., 1.6 * rms**.5), 3) if math.isfinite(rms) else 0.


def _clip_levels(audio: bytes) -> tuple[list[float], float]:
    """RMS across all PCM channels, in ~50 ms bins. Cap the size of a single desktop event."""
    try:
        with wave.open(io.BytesIO(audio)) as w:
            width, rate, frames = w.getsampwidth(), w.getframerate(), w.getnframes()
            # In 24-bit PCM the upper 16 bits are ample for a visual level.
            fmt, full_scale = {1: ("<B", 128), 2: ("<h", 32768), 3: ("<xh", 32768), 4: ("<i", 2**31)}[width]
            step = _level_step(rate, frames)
            levels = []
            while block := w.readframes(step):
                samples = struct.iter_unpack(fmt, block)
                if width == 1:              # 8-bit WAV stores silence at 128; wider samples are signed
                    energy = sum((v - 128)**2 for (v,) in samples)
                else:
                    energy = sum(v * v for (v,) in samples)
                rms = (energy / (len(block) // width))**.5 / full_scale
                levels.append(_visual_level(rms))
            return levels, step * 1000 / rate
    except Exception:
        pass

    # Python's wave reader doesn't accept IEEE float WAV, also common in TTS.
    # Load the app's audio decoder only for WAV variants that need it.
    if audio[:4] in (b"RIFF", b"RF64") and audio[8:12] == b"WAVE":
        try:
            import av
            import numpy as np

            with av.open(io.BytesIO(audio), format="wav") as source:
                stream = source.streams.audio[0]
                rate = stream.codec_context.sample_rate
                frames = round((stream.duration or 0) * stream.time_base * rate)
                step = _level_step(rate, frames)
                bins = av.AudioResampler(format="flt", layout=stream.codec_context.layout, rate=rate, frame_size=step)
                levels = []
                for frame in itertools.chain(source.decode(stream), (None,)):  # flush the final partial bin
                    for block in bins.resample(frame):
                        if len(levels) >= 2400:  # guard inaccurate duration metadata
                            return [], 50.
                        power = np.square(block.to_ndarray(), dtype=np.float64).mean()
                        levels.append(_visual_level(math.sqrt(power)))
                return levels, step * 1000 / rate
        except Exception:
            pass
    return [], 50.                          # unsupported audio may still play in the native player


class _Item:
    """One voice clip plus the text blocks that go with it. `parts` = [(weight, show_fn)]: the first block is shown
    when the audio starts, the others are paced over the clip's length, so the words follow the voice.
    Every part runs exactly once; fire() shows whatever is left (stop, fallback, server down)."""
    __slots__ = ("ep", "text", "parts", "idx", "audio", "finished", "owner", "lk", "shown_at")

    def __init__(self, owner, ep: int, text, parts) -> None:
        self.owner, self.ep, self.text, self.parts = owner, ep, text, list(parts)
        self.idx = 0
        self.audio = None
        self.shown_at = 0.0                 # when the last of its words went on screen
        self.finished = False
        self.lk = threading.Lock()

    def _show_upto(self, n: int) -> None:
        while True:
            with self.lk:
                if self.idx >= min(n, len(self.parts)):
                    return
                fn = self.parts[self.idx][1]
                self.idx += 1
                done = self.idx >= len(self.parts)
            try:
                fn()
            except Exception:
                pass
            if done:
                self.shown_at = time.time()
                self.owner._shown_one()

    def fire(self) -> None:
        self._show_upto(len(self.parts))

    def start(self, dur: float) -> None:
        self._show_upto(1)
        if len(self.parts) > 1:
            threading.Thread(target=self._pace, args=(dur,), daemon=True).start()

    def _pace(self, dur: float) -> None:
        total = sum(w for w, _ in self.parts) or 1
        t0, cum = time.time(), 0
        for i in range(1, len(self.parts)):
            cum += self.parts[i - 1][0]
            at = t0 + dur * cum / total
            while time.time() < at:
                if self.idx >= len(self.parts) or self.ep != self.owner.epoch:
                    return
                time.sleep(0.05)
            self._show_upto(i + 1)

    def fin(self) -> None:
        if self.finished:
            return
        self.finished = True
        with self.owner._lock:
            self.owner._n = max(0, self.owner._n - 1)
        self.owner._ph()


class Voice:
    def __init__(self) -> None:
        self.q: queue.Queue = queue.Queue()
        self.epoch = 0                      # bumped by stop(): in-flight work is discarded
        self.proc: subprocess.Popen | None = None
        self.server: subprocess.Popen | None = None     # only set if WE started it
        self.thread: threading.Thread | None = None
        self.notify = None                  # callable(str) -> shows a dim note in the UI
        self.last_error = ""
        self._noted = ""
        self._pid_cache: dict[str, str] = {}
        self.busy = False
        self.story = False                  # this turn is a bedtime-story request: always tell it aloud
        self.pq: queue.Queue = queue.Queue()            # generated audio waiting to be played
        self.player: threading.Thread | None = None
        self.playing = False
        self._lock = threading.Lock()
        self._n = 0                         # items not yet finished (queued, generating or playing)
        self._gen = None                    # the item being generated right now
        self._unshown = 0                   # items whose text is not fully on screen yet
        self._srv_lock = threading.Lock()
        self.on_phase = None                # callable(str): told when the voice goes quiet / replying / speaking
        self.on_clip = None                 # desktop callback(levels, bin_ms, playback_start_ms), once per clip
        self._ph_last = ""
        self._warm_done = threading.Event()  # set unless a warm-up clip is being generated
        self._warm_done.set()
        self._warm_at = 0.0                 # when the voice was last warmed up
        self._batch: list = []              # this reply's blocks, spoken together when the reply is complete

    # ------------------------------------------------------------ settings
    @property
    def enabled(self) -> bool:
        return bool(_cfg("voice", False))

    @property
    def mode(self) -> str:
        return _cfg("voice_mode", "say")

    @property
    def lang(self) -> str:
        return _cfg("voice_lang", "ja")

    @property
    def url(self) -> str:
        return _cfg("voice_url", "http://127.0.0.1:17493").rstrip("/")

    def set(self, **kv) -> None:
        effort.save_settings(**kv)

    def voice_text(self) -> bool:
        """True when the words are shown as the voice speaks them (so the raw streaming text stays hidden)."""
        return bool(self.enabled or self.story)

    def phase(self) -> str:
        """'' (quiet), 'replying' (queued/generating, nothing audible yet) or 'speaking' (audio playing)."""
        if not self.speaking():
            return ""
        return "speaking" if self.playing else "replying"

    def _ph(self) -> None:
        p = self.phase()
        if p == self._ph_last:
            return
        self._ph_last = p
        cb = self.on_phase
        if cb:
            try:
                cb(p)
            except Exception:
                pass

    def speaking(self) -> bool:
        return (self._n > 0 or self.busy or self.playing or not self.q.empty() or not self.pq.empty()
                or (self.proc is not None and self.proc.poll() is None))

    # ------------------------------------------------------------ prompt
    def prompt_section(self) -> str:
        lang = LANG_NAMES.get(self.lang, self.lang)
        if self.story:
            return ("# Bedtime story (read aloud)\nThe user asked for a bedtime story / fairy tale. Tell it in a calm, soft, "
                    f"soothing voice, in {lang}, because it will be read aloud. Start with ONE short sentence in the user's "
                    f"language announcing the story. Then write the story as 5 to 8 short paragraphs of two or three simple "
                    f"sentences each, and wrap EVERY paragraph in its own <say>...</say> tag on its own line, separated by a blank line. "
                    "Plain words only inside <say>: no emoji, markup or sound effects. Finish with a gentle goodnight line in the last <say>.")
        if not self.enabled:
            return ("# Your voice\nYou DO have a real voice (a text-to-speech voice made for you), but it is switched off right now. "
                    "If the user asks whether you can talk or have a voice, say yes, warmly, and tell them to type /voice on to hear you "
                    "(or /talk for a hands-free call). Never claim you are text only or cannot speak.")
        base = ("# Your voice\nYou have a real voice, and it is ON: what you write is spoken aloud to the user in your own voice, "
                "so they hear you. You CAN speak and be heard. Never say that you have no voice, cannot speak, cannot make sounds, "
                "or are only text; if asked, say yes, you can talk, and answer warmly in character. ")
        if self.mode != "say":
            return (base + "Your whole reply is read aloud, so write the way you speak: natural spoken sentences, no tables, lists or code "
                    f"in the spoken parts. Spoken language: {lang}. Actions in *asterisks* are shown on screen but are not spoken.")
        return (base + "\n\n# Voice mode\nWrite your normal answer first, in the user's language. Then add ONE final line of the form "
                f"<say>...</say> containing one or two short, natural, warm spoken sentences in {lang} that "
                "sum up your answer. Inside <say> use plain words only: no code, file paths, URLs, emoji or markup, and no "
                "*actions* or (stage directions): only words that are actually spoken.")

    # ------------------------------------------------------------ text handling
    def handle(self, text: str) -> str:
        """Called for every finished block of the reply. Speaks what should be spoken and returns the
        text to display (<say> tags become a '♪ ' line)."""
        says = SAY_RE.findall(text)
        shown = SAY_RE.sub(lambda m: "♪ " + m.group(1).strip(), text) if says else text
        if self.enabled or self.story:
            if self.mode == "say" or self.story:
                for s in says:
                    self.speak(clean_for_speech(s, 300))
            else:
                self.speak(clean_for_speech(shown))
        return shown

    # ------------------------------------------------------------ playing
    def _shown_one(self) -> None:
        with self._lock:
            self._unshown = max(0, self._unshown - 1)

    def _enqueue(self, item) -> None:
        with self._lock:
            self._n += 1
            if item.parts:
                self._unshown += 1
        self.q.put(item)
        self._ph()
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()

    def speak(self, text: str, show=None) -> None:
        parts = [(len(text or ""), show)] if show else []
        if not text or len(text) < 2:
            if show:
                self.defer(show)
            return
        self._enqueue(_Item(self, self.epoch, text, parts))

    def defer(self, show) -> None:
        """Run `show` after everything already queued has been shown (at once if nothing is pending)."""
        if self._batch:                      # the reply is still being collected: this goes after it, in order
            with self._lock:
                self._batch.append((None, show))
        elif self._n <= 0:
            show()
        else:
            self._enqueue(_Item(self, self.epoch, None, [(0, show)]))

    def present(self, text: str, show) -> None:
        """Take one finished block of the reply. With the voice on it is held until the reply is complete (flush),
        then spoken together with the other blocks as ONE clip, and shown as the voice reaches it."""
        says = SAY_RE.findall(text)
        shown = SAY_RE.sub(lambda m: "\u266a " + m.group(1).strip(), text) if says else text
        texts = []
        if self.enabled or self.story:
            if self.mode == "say" or self.story:
                texts = [clean_for_speech(x, 300) for x in says]
            else:
                texts = [clean_for_speech(shown)]
            texts = [x for x in texts if len(x) >= 2]
        speech = " ".join(texts) or None

        def first():
            show(shown)

        if self.voice_text() or self._batch:
            with self._lock:
                self._batch.append((speech, first))
        else:
            self.defer(first)

    def flush(self) -> None:
        """The reply is complete: speak its blocks as one clip (a long reply as a few) and start showing them."""
        with self._lock:
            batch, self._batch = self._batch, []
        if not batch:
            return
        groups, cur, n = [], [], 0
        for sp, fn in batch:
            ln = len(sp) if sp else 0
            if cur and n > 0 and n + ln > (CHUNK if groups else FIRST_CHUNK):
                groups.append(cur)
                cur, n = [], 0
            cur.append((sp, fn))
            n += ln
        if cur:
            groups.append(cur)
        for g in groups:
            text = " ".join(sp for sp, _ in g if sp)
            parts = [(len(sp) if sp else 0, fn) for sp, fn in g]
            if not text and self._n <= 0:
                for _, fn in parts:
                    try:
                        fn()
                    except Exception:
                        pass
                continue
            pieces = _split_speech(text) if text else [text]
            self._enqueue(_Item(self, self.epoch, pieces[0] if len(pieces[0] or "") >= 2 else None, parts))
            for extra in pieces[1:]:                    # the rest follows as clips of its own; the words are already shown
                self._enqueue(_Item(self, self.epoch, extra, []))

    def warm(self) -> None:
        """Get the voice ready before the reply is: start the server and run one tiny clip through the model (the first
        generation after loading is the slow one), in the background. At most once every few minutes."""
        if not self.enabled or self.busy or self._n > 0 or time.time() - self._warm_at < 300:
            return
        self._warm_at = time.time()
        ep = self.epoch

        self._warm_done.clear()

        def go():
            try:
                self._say(ep, "Mm.")
            except Exception:
                pass
            finally:
                self._warm_done.set()
        threading.Thread(target=go, daemon=True).start()

    def sync(self, timeout: float = 60.0) -> None:
        """Wait until the reply's text is on screen (not until the voice has finished), so whatever the agent
        prints next (tool output ...) cannot appear before the words that came first."""
        try:
            self.flush()
            end = time.time() + timeout
            while self._unshown > 0 and time.time() < end:
                time.sleep(0.05)
        except Exception:
            pass

    def stop(self) -> None:
        """Silence immediately and forget everything queued. Text still waiting for its voice is shown now."""
        self.epoch += 1
        items = []
        if self._gen is not None:
            items.append(self._gen)
        for qq in (self.pq, self.q):
            try:
                while True:
                    items.append(qq.get_nowait())
            except queue.Empty:
                pass
        for it in items:
            it.fire()
            it.fin()
        with self._lock:
            batch, self._batch = self._batch, []
        for _, fn in batch:
            try:
                fn()
            except Exception:
                pass
        p = self.proc
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except OSError:
                pass
        self._ph()

    def _note(self, msg: str) -> None:
        self.last_error = msg
        if msg != self._noted and self.notify:
            self._noted = msg
            try:
                self.notify(msg)
            except Exception:
                pass

    def _worker(self) -> None:
        """Generator: turns queued clips into audio and hands them to the player (stays ahead of playback)."""
        while True:
            try:
                item = self.q.get(timeout=60)
            except queue.Empty:
                return
            if item.ep != self.epoch:
                item.fire()
                item.fin()
                continue
            if item.text is not None:
                self._gen = item
                self.busy = True
                self._ph()
                timer = threading.Timer(25.0 + len(item.text) * 0.1, item.fire)    # never keep the words back for long
                timer.daemon = True
                timer.start()
                try:
                    # (no early fire when the server looks down: alive() can time out while it is busy generating, and
                    #  showing everything then left the voice minutes behind. The timer above bounds the wait.)
                    self._warm_done.wait(90)                # queued behind the warm-up it would only wait in the server anyway
                    item.audio = self._say(item.ep, item.text)
                except Exception as e:                      # voice must never break the agent
                    self._note(f"voice: {type(e).__name__}: {e}"[:160])
                finally:
                    timer.cancel()
                    self.busy = False
                    self._gen = None
                    self._ph()
            if item.ep != self.epoch:
                item.fire()
                item.fin()
                continue
            self.pq.put(item)
            if self.player is None or not self.player.is_alive():
                self.player = threading.Thread(target=self._player, daemon=True)
                self.player.start()

    def _player(self) -> None:
        while True:
            try:
                item = self.pq.get(timeout=30)
            except queue.Empty:
                return
            if item.ep != self.epoch:
                item.fire()
                item.fin()
                continue
            if item.audio and item.parts and item.shown_at and time.time() - item.shown_at > LATE_S:
                item.audio = None                           # the words have long been on screen: reading them now would be out of sync
                self._note(tr_('voice: the voice came too late for its text and was skipped'))
            if item.audio:
                item.start(_duration(item.audio, item.text or ""))      # words follow the voice
                try:
                    self._play(item.audio, item.ep)
                except Exception as e:
                    self._note(f"voice: {type(e).__name__}: {e}"[:160])
                finally:
                    self.playing = False
            else:
                item.fire()
            item.fin()
            self._ph()

    # ------------------------------------------------------------ server
    def _get(self, path: str, timeout: float = 5):
        return urllib.request.urlopen(self.url + path, timeout=timeout)

    def alive(self) -> bool:
        try:
            self._get("/profiles", 4).read()
            return True
        except Exception:
            return False

    def start_server(self) -> bool:
        d = Path(_cfg("voice_dir", str(Path.home() / "voicebox"))).expanduser()
        py = d / "backend" / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not py.exists():
            return False
        LOG.parent.mkdir(parents=True, exist_ok=True)
        host, port = self.url.split("//")[1].split(":")
        self.server = subprocess.Popen([str(py), "-m", "backend.main", "--host", host, "--port", port],
                                       cwd=str(d), stdout=open(LOG, "ab"), stderr=subprocess.STDOUT,
                                       **_detach())
        return True

    def ensure_server(self, ep: int) -> bool:
        with self._srv_lock:                # the warm-up and a real clip must not both start a server
            return self._ensure_server(ep)

    def _ensure_server(self, ep: int) -> bool:
        if self.alive():
            return True
        if not self.start_server():
            self._note(tr_('voice: Voicebox server not running and not found (set voice_dir, see /voice)'))
            return False
        self._note(tr_('voice: starting the Voicebox server (about 30 s the first time)…'))
        for _ in range(90):
            if ep != self.epoch:
                return False
            time.sleep(1)
            if self.alive():
                self._noted = ""
                return True
        self._note(tr_('voice: the Voicebox server did not come up (see ~/.emilie/voicebox.log)'))
        return False

    def profile_id(self) -> str | None:
        name = _cfg("voice_profile", "Emilie")
        if name in self._pid_cache:
            return self._pid_cache[name]
        for p in json.load(self._get("/profiles")):
            if name.lower() in (p.get("name", "").lower(), p.get("id", "")):
                self._pid_cache[name] = p["id"]
                return p["id"]
        self._note(tr_("voice: no voice profile named '{name}' (/voice profile <name>)", name=name))
        return None

    def _say(self, ep: int, text: str) -> bytes | None:
        if not self.ensure_server(ep) or ep != self.epoch:
            return None
        pid = self.profile_id()
        if not pid:
            return None
        body = json.dumps({"profile_id": pid, "text": text, "language": self.lang,
                           "engine": _cfg("voice_engine", "qwen"), "model_size": _cfg("voice_size", "0.6B")}).encode()
        req = urllib.request.Request(self.url + "/generate", body, {"Content-Type": "application/json"})
        gen = json.load(urllib.request.urlopen(req, timeout=30))["id"]
        status = "generating"
        deadline = time.time() + 75 + len(text) * 0.25      # a warm model takes seconds; the first clip after loading needs ~35 s more
        with self._get(f"/generate/{gen}/status", 15) as r:
            while True:
                try:
                    raw = r.readline()
                except Exception:                           # read timeout: no update for 15 s
                    raw = b""
                if ep != self.epoch:
                    return None
                if time.time() > deadline:
                    try:                                    # free the GPU for the next sentence
                        urllib.request.urlopen(urllib.request.Request(self.url + f"/generate/{gen}/cancel", b"", method="POST"), timeout=5)
                    except Exception:
                        pass
                    self._note(tr_('voice: that sentence took too long and was skipped'))
                    return None
                line = raw.decode("utf-8", "ignore").strip()
                if line.startswith("data:"):
                    d = json.loads(line[5:])
                    status = d.get("status", status)
                    if status in ("completed", "failed"):
                        if status == "failed":
                            self._note(tr_('voice: generation failed: ') + str(d.get("error"))[:120])
                            return None
                        break
        if status != "completed" or ep != self.epoch:
            return None
        audio = self._get(f"/audio/{gen}", 30).read()
        self._noted = ""
        return audio

    def _play(self, audio: bytes, ep: int) -> None:
        for cmd in (["mpv", "--no-video", "--really-quiet"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"],
                    ["aplay", "-q"]):
            if shutil.which(cmd[0]):
                break
        else:
            if os.name == "nt":      # built-in fallback: PowerShell's WAV player
                cmd = ["powershell", "-NoProfile", "-Command"]
            else:
                self._note(tr_('voice: no audio player found (install mpv)'))
                return
        on_clip = self.on_clip
        levels, interval = _clip_levels(audio) if on_clip else ([], 50.)

        def started(elapsed: float = 0.) -> None:
            if ep != self.epoch:
                return
            at = round((time.time() - elapsed) * 1000)
            self.playing = True
            self._ph()
            if on_clip:
                try:
                    on_clip(levels, interval, at)
                except Exception:
                    pass                    # an unavailable renderer must never interrupt playback

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio)
        try:
            if ep != self.epoch:
                return
            player = cmd[0]
            env = None
            marker = "EMILIE_PLAYING"
            if on_clip and player == "mpv":
                cmd = [player, "--no-video", "--terminal=yes", "--quiet", "--msg-color=no", f"--term-playing-msg={marker}"]
            elif on_clip and player == "ffplay":
                cmd.append("-stats")        # audio clock accounts for process startup and device buffering
            elif on_clip and player == "aplay":
                cmd = [player]              # aplay announces the opened stream on stderr
                env = {**os.environ, "LC_ALL": "C"}
            if player == "powershell":
                path = f.name.replace("'", "''")
                ready = f"$p.Load(); [Console]::Out.WriteLine('{marker}'); " if on_clip else ""
                cmd.append(f"$ErrorActionPreference='Stop'; $p=New-Object Media.SoundPlayer '{path}'; {ready}$p.PlaySync()")
            else:
                cmd.append(f.name)
            with subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE if on_clip else subprocess.DEVNULL,
                                  stderr=subprocess.STDOUT if on_clip else subprocess.DEVNULL, env=env) as proc:
                self.proc = proc
                if ep != self.epoch:        # stop() may have run while the player process was starting
                    proc.terminate()
                elif not on_clip:
                    started()
                else:
                    # ffplay terminates its clock updates with CR; don't wait another frame for a newline.
                    with io.TextIOWrapper(proc.stdout, encoding="ascii", errors="replace",
                                          newline="\r" if player == "ffplay" else None) as output:
                        for line in output:
                            if self.playing or ep != self.epoch:
                                continue
                            if player == "ffplay":
                                match = re.match(r"\s*(\d+\.\d+) M-A:", line)
                                if match:
                                    started(float(match[1]))
                                elif 0 < len(levels) * interval <= 160 and " M-A:" in line:
                                    # A clip shorter than the output buffer can finish before the first
                                    # numeric clock update. The audio output has already opened here.
                                    started()
                            elif marker in line or (player == "aplay" and line.startswith("Playing ")):
                                started()
        finally:
            try:
                os.unlink(f.name)
            except OSError:
                pass

    def stop_server(self) -> bool:
        p = self.server
        if p is not None and p.poll() is None:
            p.terminate()
            return True
        return False

    # ------------------------------------------------------------ commands
    def toggle(self) -> str:
        on = not self.enabled
        self.set(voice=on)
        if not on:
            self.stop()
        return "voice " + ("on" if on else "off")

    def status_lines(self) -> list[str]:
        return [tr_('voice: {0}   mode: {1}   language: {2}   profile: {3}', 'on' if self.enabled else 'off', self.mode, self.lang, _cfg('voice_profile', 'Emilie')),
                f"server: {self.url}  ({'running' if self.alive() else tr_('not running')})"
                + (tr_('   last note: {0}', self.last_error) if self.last_error else "")]


VOICE = Voice()
