"""Voice output: the agent's reply is spoken by a local Voicebox server (cloned voice).

Flow:  reply finished -> <say> line (or whole reply) -> POST /generate -> wait -> GET /audio -> play.
Everything runs in a background thread, so the terminal never blocks. If the server is down, Emilie
keeps working silently (one note is shown).

Settings (~/.emilie/settings.json): voice, voice_mode (say|full), voice_lang, voice_profile,
voice_url, voice_dir, voice_engine, voice_size.
"""
from . import paths
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
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
    t = re.sub(r"[#*_>|~\[\]{}<>=]+", " ", t)
    t = re.sub(r"[\U00010000-\U0010ffff☀-➿]", " ", t)        # emoji / dingbats
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit]


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

    def speaking(self) -> bool:
        return (self.busy or self.playing or not self.q.empty() or not self.pq.empty()
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
        if not self.enabled or self.mode != "say":
            return ""
        return ("# Voice mode\nYour replies are also spoken aloud in a cute anime-girl voice. "
                "Write your normal answer first, in the user's language. Then add ONE final line of the form "
                f"<say>...</say> containing one or two short, natural, warm spoken sentences in {lang} that "
                "sum up your answer. Inside <say> use plain words only: no code, file paths, URLs, emoji or markup.")

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
    def speak(self, text: str) -> None:
        if not text or len(text) < 2:
            return
        self.q.put((self.epoch, text))
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()

    def stop(self) -> None:
        """Silence immediately and forget everything queued."""
        self.epoch += 1
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass
        try:
            while True:
                self.pq.get_nowait()
        except queue.Empty:
            pass
        p = self.proc
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except OSError:
                pass

    def _note(self, msg: str) -> None:
        self.last_error = msg
        if msg != self._noted and self.notify:
            self._noted = msg
            try:
                self.notify(msg)
            except Exception:
                pass

    def _worker(self) -> None:
        """Generator: turns queued sentences into audio and hands them to the player (stays ahead of playback)."""
        while True:
            try:
                ep, text = self.q.get(timeout=60)
            except queue.Empty:
                return
            if ep != self.epoch:
                continue
            self.busy = True
            try:
                audio = self._say(ep, text)
                if audio and ep == self.epoch:
                    self.pq.put((ep, audio))
                    if self.player is None or not self.player.is_alive():
                        self.player = threading.Thread(target=self._player, daemon=True)
                        self.player.start()
            except Exception as e:                      # voice must never break the agent
                self._note(f"voice: {type(e).__name__}: {e}"[:160])
            finally:
                self.busy = False

    def _player(self) -> None:
        while True:
            try:
                ep, audio = self.pq.get(timeout=30)
            except queue.Empty:
                return
            if ep != self.epoch:
                continue
            self.playing = True
            try:
                self._play(audio, ep)
            except Exception as e:
                self._note(f"voice: {type(e).__name__}: {e}"[:160])
            finally:
                self.playing = False

    # ------------------------------------------------------------ server
    def _get(self, path: str, timeout: float = 5):
        return urllib.request.urlopen(self.url + path, timeout=timeout)

    def alive(self) -> bool:
        try:
            self._get("/profiles", 2).read()
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
        deadline = time.time() + 40 + len(text) * 1.0       # a sentence should take seconds, never minutes
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
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio)
        try:
            if ep != self.epoch:
                return
            tail = [f"(New-Object Media.SoundPlayer '{f.name}').PlaySync()"] if cmd[0] == "powershell" else [f.name]
            self.proc = subprocess.Popen([*cmd, *tail], stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.proc.wait()
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
