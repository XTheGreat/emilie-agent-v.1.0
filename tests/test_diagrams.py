"""Tests for the render_diagram tool.   python -m unittest discover -s tests -v

Tests that need a real renderer are skipped when it is not installed. The others use a stand-in renderer or a local
stand-in Kroki server, so they run everywhere.
"""
import json
import os
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

from emilie import diagrams, tools

FLOW = "flowchart TD\n  A[Start] --> B{OK?}\n  B -->|yes| C[Done]\n  B -->|no| A\n"
SEQ = "@startuml\nAlice -> Bob: hello\nBob --> Alice: hi\n@enduml\n"
HAS_MERMAID = bool(shutil.which("mmdc"))
HAS_PLANTUML = bool(shutil.which("plantuml") and shutil.which("java"))


def call(**args) -> dict:
    return json.loads(tools.invoke("render_diagram", args))


class InTempDir(unittest.TestCase):
    def setUp(self):
        old = os.getcwd()
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(os.chdir, old)                 # runs before the cleanup above
        self.root = Path(tmp.name).resolve()
        self.work = self.root / "project"
        self.work.mkdir()
        os.chdir(self.work)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("KROKI_URL", None)


class Validation(InTempDir):
    def test_registered(self):
        # TOOLS, not SCHEMAS: SCHEMAS picks up the later tool modules when the agent registers its own tools
        self.assertEqual(tools.TOOLS["render_diagram"][1]["input_schema"]["required"], ["code", "kind"])

    def test_unknown_kind_and_fmt(self):
        for args in ({"kind": "dot"}, {"kind": "mermaid", "fmt": "pdf"}):
            out = call(code=FLOW, **args)
            self.assertFalse(out["ok"])
            self.assertIn("unknown", out["error"])
        self.assertFalse((self.work / "diagrams").exists())

    def test_empty_and_too_large(self):
        self.assertIn("empty", call(code="  ", kind="mermaid")["error"])
        self.assertIn("100 KB", call(code="x" * (diagrams.MAX_CODE_BYTES + 1), kind="mermaid")["error"])

    def test_missing_renderer_says_how_to_install(self):
        with mock.patch.object(diagrams.shutil, "which", return_value=None):
            self.assertIn("npm install -g @mermaid-js/mermaid-cli", call(code=FLOW, kind="mermaid")["error"])
            error = call(code=SEQ, kind="plantuml")["error"]
        self.assertIn("plantuml is not installed", error)
        self.assertIn("java is not installed", error)

    def test_safe_name(self):
        for bad, good in {"../../x": "x.svg", "..\\..\\x.svg": "x.svg", "/etc/passwd": "passwd.svg",
                          "C:\\Windows\\a b&c": "a_b_c.svg", "con": "_con.svg", "-rf": "rf.svg"}.items():
            self.assertEqual(diagrams.safe_name(bad, "code", "svg"), good, bad)
        for empty in ("", "..", "../..", "///"):
            self.assertRegex(diagrams.safe_name(empty, "code", "png"), r"^diagram-[0-9a-f]{8}\.png$")


class StandInRenderer(InTempDir):
    """The whole path of a call with the subprocess replaced."""

    def setUp(self):
        super().setUp()
        which = mock.patch.object(diagrams.shutil, "which", side_effect=lambda n: f"/bin/{n}")
        which.start()
        self.addCleanup(which.stop)
        self.calls = []

    def renderer(self, rc=0, log="", writes=None):
        def run(cmd, cwd, env=None):
            self.calls.append((cmd, cwd, env))
            if writes:
                (Path(cwd) / writes).write_text("<svg/>")
            return rc, log
        return mock.patch.object(diagrams, "_run", side_effect=run)

    def test_dangerous_filename_stays_inside_diagrams(self):
        with self.renderer(writes="out.svg"):
            out = call(code=FLOW, kind="mermaid", filename="../../x")
        self.assertEqual(Path(out["path"]), self.work / "diagrams" / "x.svg")
        self.assertEqual(sorted(p.name for p in self.root.rglob("*.svg")), ["x.svg"])
        cmd, cwd, _ = self.calls[0]
        self.assertEqual(cmd[1:], ["-i", "in.mmd", "-o", "out.svg"])
        self.assertFalse(Path(cwd).exists(), "temporary folder was not removed")

    def test_error_text_comes_back_whole(self):
        log = "Parse error on line 2:\n...A -->> ??\nExpecting 'SQE'"
        with self.renderer(rc=1, log=log):
            out = call(code="flowchart TD\n A -->> ??", kind="mermaid")
        self.assertEqual(out, {"ok": False, "error": log})
        self.assertFalse(Path(self.calls[0][1]).exists())

    def test_no_sandbox_only_after_a_sandbox_error(self):
        def run(cmd, cwd, env=None):
            self.calls.append(cmd)
            if "-p" not in cmd:
                return 1, "No usable sandbox!"
            self.assertIn("--no-sandbox", (Path(cwd) / "puppeteer.json").read_text())
            (Path(cwd) / "out.svg").write_text("<svg/>")
            return 0, ""
        with mock.patch.object(diagrams, "_run", side_effect=run):
            self.assertTrue(call(code=FLOW, kind="mermaid")["ok"])
        self.assertEqual(len(self.calls), 2)

    def test_plantuml_source_cannot_choose_the_output_path(self):
        seen = []

        def run(cmd, cwd, env=None):
            seen.append(((Path(cwd) / "in.puml").read_text(), env["PLANTUML_SECURITY_PROFILE"]))
            (Path(cwd) / "in.svg").write_text("<svg/>")
            return 0, ""
        os.environ.pop("PLANTUML_SECURITY_PROFILE", None)
        with mock.patch.object(diagrams, "_run", side_effect=run):
            call(code="@startuml ../../evil\nA -> B\n@enduml", kind="plantuml")
            call(code="A -> B", kind="plantuml")
        self.assertEqual(seen[0], ("@startuml\nA -> B\n@enduml", "SANDBOX"))
        self.assertTrue(seen[1][0].startswith("@startuml\nA -> B"))

    def test_plantuml_error_picture_is_not_a_success(self):
        with self.renderer(rc=200, log="Syntax Error? (line 2)", writes="in.svg"):
            out = call(code="@startuml\n???\n@enduml", kind="plantuml")
        self.assertEqual(out, {"ok": False, "error": "Syntax Error? (line 2)"})
        self.assertEqual(list((self.work / "diagrams").iterdir()), [])

    def test_plantuml_error_with_exit_code_zero(self):
        log = "Error line 2 in file: in.puml\nSome diagram description contains errors"
        with self.renderer(rc=0, log=log, writes="in.svg"):
            out = call(code="@startuml\n???\n@enduml", kind="plantuml")
        self.assertEqual(out, {"ok": False, "error": log})


class Timeout(InTempDir):
    def test_a_stuck_renderer_is_stopped(self):
        import sys
        with mock.patch.object(diagrams, "TIMEOUT", 1), self.assertRaisesRegex(diagrams.RenderError, "within 1s"):
            diagrams._run([sys.executable, "-c", "import time; time.sleep(30)"], str(self.work))


class Kroki(InTempDir):
    def setUp(self):
        super().setUp()
        seen = self.seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"])).decode()
                seen.append((self.path, body))
                bad = "broken" in body
                self.send_response(400 if bad else 200)
                self.end_headers()
                self.wfile.write(b"Error 400: syntax error in line 1" if bad else b"<svg>kroki</svg>")

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        os.environ["KROKI_URL"] = f"http://127.0.0.1:{server.server_port}/"
        which = mock.patch.object(diagrams.shutil, "which", return_value=None)
        which.start()
        self.addCleanup(which.stop)

    def test_fallback_and_its_error(self):
        out = call(code=FLOW, kind="mermaid", filename="k")
        self.assertEqual(Path(out["path"]).read_text(), "<svg>kroki</svg>")
        self.assertEqual(self.seen[0], ("/mermaid/svg", FLOW))
        bad = call(code="broken", kind="plantuml")
        self.assertFalse(bad["ok"])
        self.assertIn("syntax error in line 1", bad["error"])


@unittest.skipUnless(HAS_MERMAID, "mmdc is not installed (npm install -g @mermaid-js/mermaid-cli)")
class RealMermaid(InTempDir):
    def test_flowchart_end_to_end(self):
        for fmt, magic in (("svg", b"<svg"), ("png", b"\x89PNG")):
            out = call(code=FLOW, kind="mermaid", fmt=fmt, filename="flow")
            self.assertTrue(out["ok"], out)
            self.assertIn(magic, Path(out["path"]).read_bytes()[:500])

    def test_syntax_error(self):
        out = call(code="flowchart TD\n  A[unclosed -->", kind="mermaid")
        self.assertFalse(out["ok"])
        self.assertIn("Parse error", out["error"])       # not just any failure, e.g. a missing browser


@unittest.skipUnless(HAS_PLANTUML, "plantuml and/or java are not installed")
class RealPlantUML(InTempDir):
    def test_sequence_end_to_end(self):
        out = call(code=SEQ, kind="plantuml", filename="seq")
        self.assertTrue(out["ok"], out)
        self.assertIn(b"<svg", Path(out["path"]).read_bytes()[:500])

    def test_syntax_error(self):
        out = call(code="@startuml\nthis is ??? not uml\n@enduml", kind="plantuml")
        self.assertFalse(out["ok"])
        self.assertTrue(out["error"])


if __name__ == "__main__":
    unittest.main()
