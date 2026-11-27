import io
import struct
import unittest
import wave

from emilie.voice import _clip_levels


class VoiceLevelsTest(unittest.TestCase):
    def test_volume_and_pauses_follow_the_clip_even_with_opposite_stereo_channels(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setparams((2, 2, 8000, 0, "NONE", "NONE"))
            # Four 100 ms sections. Downmixing these channels before measuring
            # their energy would make the entire recording appear silent.
            for amplitude in (0, 1200, 16000, 0):
                positive = struct.pack("<hh", amplitude, -amplitude)
                negative = struct.pack("<hh", -amplitude, amplitude)
                wav.writeframes((positive * 20 + negative * 20) * 20)

        levels, interval = _clip_levels(audio.getvalue())
        self.assertAlmostEqual(len(levels) * interval, 400, delta=interval)
        silence, soft, loud, pause = (levels[int(ms / interval)] for ms in (40, 140, 240, 340))
        self.assertLess(silence, .02)
        self.assertLess(pause, .02)
        self.assertGreater(soft, .02)
        self.assertGreater(loud, soft)
        self.assertLessEqual(loud, 1)

    def test_unreadable_clip_has_no_measured_signal(self):
        levels, _ = _clip_levels(b"")
        self.assertEqual(levels, [])
