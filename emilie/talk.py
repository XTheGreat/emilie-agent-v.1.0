"""Hands-free conversation mode ("phone call"): the mic stays open, a pause in your speech ends your turn.

  mic (parec/arecord, raw 16 kHz) -> voice-activity detection -> pause = end of utterance
  -> Voicebox /transcribe (Whisper, local) -> sent to the agent like a typed message.

While the agent works or its voice is playing, the mic is ignored (no echo loop). Nothing leaves the machine:
transcription runs in the local Voicebox server.

Settings: talk_pause (seconds of silence that end a turn, default 1.0), talk_lang ("" = auto-detect),
talk_model (whisper size, default "base"), talk_sens (1.0 = normal; lower = more sensitive),
talk_cmd (override the capture command, used by tests).
"""
import collections
import io
import json
import shlex
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave

import numpy as np

from .i18n import t as tr_
from . import voice
from .voice import VOICE, _cfg

RATE = 16000
FRAME = 480                      # 30 ms
FBYTES = FRAME * 2
HALLUCINATIONS = (
    "thank you", "thanks for watching", "ご視聴ありがとうございました", "ご視聴ありがとうございます", "字幕",
    "subtitles by", "terima kasih telah menonton", "terima kasih sudah menonton", "bye", "you")


def capture_cmd() -> list[str] | None:
    custom = _cfg("talk_cmd", "")
    if custom:
        return shlex.split(custom) if isinstance(custom, str) else list(custom)
    if shutil.which("parec"):
        return ["parec", "--format=s16le", "--rate=16000", "--channels=1", "--raw", "--latency-msec=30"]
    if shutil.which("arecord"):
        return ["arecord", "-q", "-t", "raw", "-f", "S16_LE", "-r", "16000", "-c", "1"]
    return None


def wav_bytes(pcm: bytes) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return b.getvalue()


def _multipart(fields: dict, fname: str, data: bytes) -> tuple[bytes, str]:
    bd = uuid.uuid4().hex
    out = b""
    for k, v in fields.items():
        out += f'--{bd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    out += (f'--{bd}\r\nContent-Disposition: form-data; name="file"; filename="{fname}"\r\n'
            f"Content-Type: audio/wav\r\n\r\n").encode() + data + f"\r\n--{bd}--\r\n".encode()
    return out, f"multipart/form-data; boundary={bd}"


class Talk:
    def __init__(self) -> None:
        self.on = False
        self.state = "off"           # off | listening | hearing | transcribing | paused
        self.proc: subprocess.Popen | None = None
        self.thread: threading.Thread | None = None
        self.submit = None           # callable(text)
        self.busy_fn = lambda: False
        self.changed = lambda: None  # UI redraw hook
        self.note = lambda m: None
        self.level = 0.0

    # ------------------------------------------------------------ control
    def start(self, submit, busy_fn, changed, note) -> str:
        if self.on:
            return tr_('talk mode already on')
        cmd = capture_cmd()
        if cmd is None:
            return tr_('talk mode: no recorder found (install pulseaudio-utils or alsa-utils)')
        self.submit, self.busy_fn, self.changed, self.note = submit, busy_fn, changed, note
        self.on = True
        self._set("listening")
        self.thread = threading.Thread(target=self._run, args=(cmd,), daemon=True)
        self.thread.start()
        return tr_('talk mode on - just speak; pause to send (/talk off to stop)')

    def stop(self) -> str:
        was = self.on
        self.on = False
        p = self.proc
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except OSError:
                pass
        self._set("off")
        return tr_('talk mode off') if was else tr_('talk mode is not running')

    def toggle(self, *a) -> str:
        return self.stop() if self.on else self.start(*a)

    def _set(self, s: str) -> None:
        if s != self.state:
            self.state = s
            try:
                self.changed()
            except Exception:
                pass

    # ------------------------------------------------------------ main loop
    def _run(self, cmd: list[str]) -> None:
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        except OSError as e:
            self.note(tr_('talk: cannot open the microphone: {e}', e=e))
            self.on = False
            self._set("off")
            return
        pause_s = float(_cfg("talk_pause", 1.0))
        sens = float(_cfg("talk_sens", 1.0))
        pause_frames = max(5, int(pause_s * 1000 / 30))
        pre = collections.deque(maxlen=10)           # 300 ms before the voice starts
        floor, speech, voiced, silent, loud = 150.0, [], 0, 0, 0
        last_busy = 0.0
        out = self.proc.stdout
        while self.on:
            data = out.read(FBYTES)
            if len(data) < FBYTES:
                break
            now = time.monotonic()
            if self.busy_fn():                       # the agent is working / talking: don't listen
                last_busy = now
                speech, voiced, silent, loud = [], 0, 0, 0
                pre.clear()
                self._set("paused")
                continue
            if now - last_busy < 0.8:                # let the echo of the voice fade
                continue
            pcm = np.frombuffer(data, dtype=np.int16)
            rms = float(np.sqrt(np.mean(pcm.astype(np.float32) ** 2)))
            self.level = rms
            thr = max(floor * 2.5, 220.0) / max(0.2, sens)
            if not speech:
                pre.append(data)
                if rms > thr:
                    loud += 1
                    if loud >= 4:                    # 120 ms of voice: a turn has started
                        speech, voiced, silent = list(pre), loud, 0
                        self._set("hearing")
                else:
                    loud = 0
                    floor = 0.97 * floor + 0.03 * rms   # adapt to room noise while idle
                    self._set("listening")
                continue
            speech.append(data)
            if rms > thr * 0.6:
                voiced += 1
                silent = 0
            else:
                silent += 1
            if silent >= pause_frames or len(speech) * 0.03 > 30:
                utter, v = b"".join(speech), voiced
                speech, voiced, silent, loud = [], 0, 0, 0
                pre.clear()
                if v >= 12:                          # at least ~0.4 s of real voice
                    self._set("transcribing")
                    try:
                        self._handle(utter)
                    except Exception as e:
                        self.note(f"talk: {type(e).__name__}: {e}"[:160])
                    last_busy = time.monotonic()
                self._set("listening" if self.on else "off")
        if self.on:                                   # the recorder ended by itself
            self.on = False
            self.note(tr_('talk mode: the microphone stream ended'))
        self._set("off")

    # ------------------------------------------------------------ speech -> text
    def transcribe(self, pcm: bytes) -> str:
        if not VOICE.ensure_server(VOICE.epoch):
            return ""
        fields = {"model": _cfg("talk_model", "base")}
        if _cfg("talk_lang", ""):
            fields["language"] = _cfg("talk_lang", "")
        body, ctype = _multipart(fields, "speech.wav", wav_bytes(pcm))
        for attempt in range(60):
            if not self.on:
                return ""
            req = urllib.request.Request(VOICE.url + "/transcribe", body, {"Content-Type": ctype})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return (json.load(r).get("text") or "").strip()
            except urllib.error.HTTPError as e:
                if e.code == 202:                     # whisper model still downloading
                    self.note(tr_('talk: the speech model is downloading, one moment…'))
                    time.sleep(5)
                    continue
                raise
        return ""

    def _handle(self, pcm: bytes) -> None:
        text = self.transcribe(pcm)
        low = text.lower().strip(" .!?。、…")
        if len(low) < 2 or any(low == h or low.startswith(h + " ") and len(low) < 40 for h in HALLUCINATIONS):
            return                                    # silence-hallucination of Whisper
        text = text.lstrip("/!#@ ")                   # spoken words must never act as commands
        if text and self.on:
            self.submit(text)


TALK = Talk()
