import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from emilie import drawio


EXAMPLE = (Path(__file__).resolve().parents[1] / "examples/contoh.drawio").read_text()


class DrawioTest(unittest.TestCase):
    def test_validation(self):
        self.assertEqual(drawio.validate(EXAMPLE), [])
        for xml, error in (("<mxfile>", "no element found"),
                           (EXAMPLE.replace('id="lookup"', 'id="check"'), "duplicate id"),
                           (EXAMPLE.replace('target="input"', 'target="absent"'), "unknown target"),
                           (EXAMPLE.replace('source="start"', 'source="absent"'), "unknown source")):
            result = json.loads(drawio.render_drawio(xml, "login"))
            self.assertFalse(result["ok"])
            self.assertIn(error, result["error"])

    def test_filename(self):
        self.assertIn("Invalid filename", json.loads(drawio.render_drawio(EXAMPLE, "../../x"))["error"])

    def export(self, fmt):
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path, "cwd", return_value=Path(tmp).resolve()):
            result = json.loads(drawio.render_drawio(EXAMPLE, "login", fmt))
            self.assertTrue(result["ok"], result)
            self.assertEqual(Path(result["drawio_path"]).read_text(), EXAMPLE)
            self.assertTrue(Path(result["image_path"]).stat().st_size)
            self.assertTrue(Path(result["image_path"]).with_suffix(".png").is_file())

    def test_export_contract(self):
        def fake(args, **kwargs):
            self.assertEqual(kwargs["timeout"], 90)
            Path(args[args.index("-o") + 1]).write_bytes(b"test")
            return type("Completed", (), {"returncode": 0})()
        with patch.object(drawio, "executable", return_value="drawio"), patch.object(drawio.subprocess, "run", fake):
            self.export("svg")

    @unittest.skipUnless(drawio.executable(), "draw.io Desktop CLI is not installed")
    def test_real_export(self):
        self.export("png")
