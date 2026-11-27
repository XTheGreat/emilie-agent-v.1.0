"""The desktop app's project panels, server side: Git, Scripts, Problems, Tests, HTTP, Ports, Notes, Database and the
background jobs they run in. Everything happens in temporary folders; nothing touches ~/.emilie."""
import http.server
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from emilie.desktop import checks, gitops, netkit, notes, projkit, scripts, sqlview, testrun

HAS_GIT = shutil.which("git") is not None


def wait(job_id: str, timeout: float = 60) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        info = projkit.job_info(job_id)
        if not info["running"]:
            return info
        time.sleep(0.05)
    raise AssertionError("job did not finish")


class Temp(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name

    def write(self, rel: str, text: str = "") -> Path:
        p = Path(self.root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p


# ---------------------------------------------------------------------------------------------------- jobs
class Jobs(Temp):
    def test_output_comes_in_pieces_and_the_result_at_the_end(self):
        def work(job):
            code, out = job.run([sys.executable, "-c", "print('one'); print('two')"])
            return {"code": code, "out": out}
        jid = projkit.start_job("t", self.root, work)["job"]
        info = wait(jid)
        self.assertEqual(info["result"]["code"], 0)
        self.assertEqual(info["lines"], ["one", "two"])
        self.assertEqual(projkit.job_info(jid, since=1)["lines"], ["two"])    # only what the panel has not seen
        self.assertEqual(projkit.job_info(jid, since=2)["lines"], [])

    def test_a_job_can_be_stopped(self):
        def work(job):
            job.run([sys.executable, "-c", "import time; print('go', flush=True); time.sleep(30)"])
        jid = projkit.start_job("t", self.root, work)["job"]
        time.sleep(0.6)
        projkit.job_stop(jid)
        info = wait(jid, 20)
        self.assertEqual(info["error"], "Stopped")
        self.assertTrue(info["stopped"])

    def test_an_unknown_job_says_so(self):
        self.assertTrue(projkit.job_info("job-nope")["gone"])

    def test_sub_projects_are_found_but_not_inside_dependencies(self):
        self.write("package.json", "{}")
        self.write("web/package.json", "{}")
        self.write("node_modules/x/package.json", "{}")
        self.write("apps/api/pyproject.toml", "")
        self.assertEqual(projkit.project_dirs(self.root, ("package.json", "pyproject.toml")), ["", "apps/api", "web"])


# ---------------------------------------------------------------------------------------------------- git
@unittest.skipUnless(HAS_GIT, "git is not installed")
class Git(Temp):
    def setUp(self):
        super().setUp()
        gitops.init(self.root)
        for k, v in (("user.name", "Test"), ("user.email", "t@example.com"), ("commit.gpgsign", "false")):
            subprocess.run(["git", "-C", self.root, "config", k, v], check=True, capture_output=True)

    def commit_all(self, msg: str) -> dict:
        info = wait(projkit.start_job("c", self.root, lambda job: gitops.commit(job, self.root, msg, all_=True))["job"])
        self.assertEqual(info["error"], "", info["lines"])
        return info["result"]

    def test_a_new_repository(self):
        st = gitops.status(self.root)
        self.assertTrue(st["repo"])
        self.assertTrue(st["initial"])
        self.assertEqual(st["commits"], [])
        self.assertFalse(gitops.status(os.path.join(self.root, "missing"))["repo"])

    def test_stage_commit_change_discard(self):
        self.write("a.txt", "one\n")
        self.write("dir with space/b.txt", "b\n")
        st = gitops.status(self.root)
        self.assertEqual(sorted(c["path"] for c in st["changed"]), ["a.txt", "dir with space/b.txt"])
        self.assertTrue(all(c["status"] == "U" for c in st["changed"]))
        gitops.stage(self.root, ["dir with space/b.txt"])
        st = gitops.status(self.root)
        self.assertEqual([c["path"] for c in st["staged"]], ["dir with space/b.txt"])
        gitops.unstage(self.root, ["dir with space/b.txt"])        # before the first commit (no HEAD yet)
        self.assertEqual(gitops.status(self.root)["staged"], [])
        res = self.commit_all("first commit")
        self.assertEqual(res["message"], "first commit")
        st = gitops.status(self.root)
        self.assertEqual((st["staged"], st["changed"]), ([], []))
        self.assertEqual(st["commits"][0]["subject"], "first commit")
        # a change, its diff, then thrown away
        self.write("a.txt", "one\ntwo\n")
        self.write("new.txt", "new\n")
        d = gitops.file_diff(self.root, "a.txt")
        self.assertEqual((d["added"], d["removed"]), (1, 0))
        self.assertIn("+two", d["text"])
        self.assertTrue(d["text"].startswith("@@"))
        u = gitops.file_diff(self.root, "new.txt", untracked=True)
        self.assertEqual(u["added"], 1)
        out = gitops.discard(self.root, ["a.txt"], ["new.txt"])
        self.assertEqual(out["deleted"], 1)
        self.assertEqual(Path(self.root, "a.txt").read_text(encoding="utf-8"), "one\n")
        self.assertFalse(Path(self.root, "new.txt").exists())

    def test_discard_never_deletes_tracked_or_ignored_files(self):
        self.write(".gitignore", "secret.txt\n")
        self.write("keep.txt", "k\n")
        self.commit_all("base")
        self.write("secret.txt", "s\n")
        gitops.discard(self.root, [], ["keep.txt", "secret.txt", "../outside.txt"])
        self.assertTrue(Path(self.root, "keep.txt").exists())
        self.assertTrue(Path(self.root, "secret.txt").exists())

    def test_rename_branch_stash_and_history(self):
        self.write("old.txt", "x\n" * 20)
        self.commit_all("add old")
        os.rename(os.path.join(self.root, "old.txt"), os.path.join(self.root, "renamed.txt"))
        gitops.stage(self.root, None)
        st = gitops.status(self.root)
        self.assertEqual(st["staged"][0]["status"], "R")
        self.assertEqual(st["staged"][0]["orig"], "old.txt")
        self.commit_all("rename it")
        files = gitops.commit_files(self.root, gitops.status(self.root)["commits"][0]["hash"])
        self.assertEqual(files["message"], "rename it")
        self.assertEqual(files["files"][0]["path"], "renamed.txt")
        self.assertEqual(files["files"][0]["status"], "R")
        # branches
        gitops.branch(self.root, "create", "feature/x")
        self.assertEqual(gitops.status(self.root)["branch"], "feature/x")
        with self.assertRaises(gitops.GitError):
            gitops.branch(self.root, "create", "bad name..")
        base = [b["name"] for b in gitops.status(self.root)["branches"] if b["name"] != "feature/x"][0]
        gitops.branch(self.root, "checkout", base)
        gitops.branch(self.root, "delete", "feature/x")
        self.assertNotIn("feature/x", [b["name"] for b in gitops.status(self.root)["branches"]])
        # stash keeps untracked files too
        self.write("wip.txt", "wip\n")
        gitops.stash(self.root, "push", message="work in progress")
        st = gitops.status(self.root)
        self.assertEqual(st["changed"], [])
        self.assertEqual(st["stashes"][0]["ref"], "stash@{0}")
        gitops.stash(self.root, "pop", "stash@{0}")
        self.assertTrue(Path(self.root, "wip.txt").exists())

    def test_publish_push_fetch_pull_with_a_remote(self):
        self.write("a.txt", "a\n")
        self.commit_all("one")
        bare = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, bare, True)
        subprocess.run(["git", "init", "-q", "--bare", bare], check=True, capture_output=True)
        subprocess.run(["git", "-C", self.root, "remote", "add", "origin", bare], check=True, capture_output=True)
        branch = gitops.status(self.root)["branch"]
        sync = lambda action: wait(projkit.start_job("s", self.root, lambda job: gitops.sync(job, self.root, action))["job"])
        info = sync("push")                                 # no upstream yet: publishes the branch
        self.assertEqual(info["error"], "", info["lines"])
        self.assertTrue(any("push -u origin" in l for l in info["lines"]))
        self.assertEqual(gitops.status(self.root)["upstream"], f"origin/{branch}")
        # someone else pushes a commit; fetch shows it as behind, pull brings it
        other = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, other, True)
        subprocess.run(["git", "clone", "-q", bare, other], check=True, capture_output=True)
        for k, v in (("user.name", "Other"), ("user.email", "o@example.com"), ("commit.gpgsign", "false")):
            subprocess.run(["git", "-C", other, "config", k, v], check=True, capture_output=True)
        Path(other, "b.txt").write_text("b\n", encoding="utf-8")
        subprocess.run(["git", "-C", other, "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", other, "commit", "-qm", "two"], check=True, capture_output=True)
        subprocess.run(["git", "-C", other, "push", "-q"], check=True, capture_output=True)
        self.assertEqual(sync("fetch")["error"], "")
        self.assertEqual(gitops.status(self.root)["behind"], 1)
        self.assertEqual(sync("pull")["error"], "")
        st = gitops.status(self.root)
        self.assertEqual((st["behind"], st["ahead"]), (0, 0))
        self.assertTrue(Path(self.root, "b.txt").exists())

    def test_push_without_a_remote_explains_itself(self):
        self.write("a.txt", "a\n")
        self.commit_all("one")
        info = wait(projkit.start_job("s", self.root, lambda job: gitops.sync(job, self.root, "push"))["job"])
        self.assertIn("no remote", info["error"])

    def test_refs_and_paths_are_checked(self):
        self.assertFalse(gitops.ref_ok("--upload-pack=x"))
        self.assertFalse(gitops.ref_ok("a..b"))
        self.assertEqual(gitops._clean(["../x", "/etc/passwd", "C:/x", "ok/a.txt"]), ["ok/a.txt"])


# ---------------------------------------------------------------------------------------------------- scripts
class Scripts(Temp):
    def test_scripts_from_the_project_files(self):
        self.write("package.json", json.dumps({"scripts": {"dev": "vite", "build": "vite build"}}))
        self.write("pnpm-lock.yaml", "")
        self.write("Makefile", "all: build ## everything\n\nbuild:\n\tgo build\n%.o: %.c\n\t$(CC)\n.PHONY: all\n")
        self.write("justfile", "# run the server\nserve port='8000':\n  python -m http.server {{port}}\n")
        self.write("pyproject.toml", '[tool.poe.tasks]\nlint = "ruff check ."\n')
        self.write("compose.yaml", "services: {}\n")
        self.write("api/Cargo.toml", "[package]\nname='x'\n")
        groups = {g["source"]: g for g in scripts.detect(self.root)["groups"]}
        dev = groups["package.json"]["items"][0]
        self.assertEqual((dev["name"], dev["command"], dev["detail"]), ("dev", "pnpm run dev", "vite"))
        self.assertEqual([(i["name"], i["detail"]) for i in groups["Makefile"]["items"]], [("all", "everything"), ("build", "")])
        self.assertEqual(groups["justfile"]["items"][0]["command"], "just serve")
        self.assertEqual(groups["justfile"]["items"][0]["detail"], "run the server")
        self.assertEqual(groups["pyproject.toml · poe"]["items"][0]["command"], "poe lint")
        self.assertIn("docker compose up", [i["command"] for i in groups["compose.yaml"]["items"]])
        self.assertEqual(groups["Cargo.toml"]["dir"], "api")

    def test_saved_commands_stay_with_their_project(self):
        with mock.patch.object(scripts, "STORE", Path(self.root) / "store" / "projects.json"):
            scripts.save_custom(self.root, [{"name": "serve", "command": "python -m http.server", "dir": "../../x"},
                                            {"name": "", "command": "  "}])
            self.assertEqual(scripts.custom(self.root), [{"name": "serve", "command": "python -m http.server", "dir": ""}])
            other = tempfile.mkdtemp()
            self.addCleanup(shutil.rmtree, other, True)
            self.assertEqual(scripts.custom(other), [])


# ---------------------------------------------------------------------------------------------------- problems
class Problems(Temp):
    def test_tsc_report(self):
        out = ("src/app.ts(3,7): error TS2322: Type 'number' is not assignable to type 'string'.\n"
               "src/b.ts(10,1): error TS2304: Cannot find name 'x'.\n  Did you mean 'y'?\n")
        p = checks.parse_tsc(out, Path(self.root), Path(self.root) / "web")
        self.assertEqual([(x["file"], x["line"], x["col"], x["code"]) for x in p],
                         [("web/src/app.ts", 3, 7, "TS2322"), ("web/src/b.ts", 10, 1, "TS2304")])
        self.assertIn("Did you mean", p[1]["message"])

    def test_eslint_ruff_pyright_reports(self):
        d = Path(self.root)
        es = checks.parse_eslint('noise\n[{"filePath": "%s", "messages": [{"ruleId": "no-unused-vars", "severity": 1, '
                                 '"message": "x is unused", "line": 2, "column": 5}]}]' % str(d / "a.js").replace("\\", "\\\\"), d, d)
        self.assertEqual((es[0]["file"], es[0]["severity"], es[0]["code"]), ("a.js", "warning", "no-unused-vars"))
        rf = checks.parse_ruff('[{"filename": "m.py", "code": "F401", "message": "os imported but unused", '
                               '"location": {"row": 1, "column": 8}}]', d, d)
        self.assertEqual((rf[0]["line"], rf[0]["col"], rf[0]["severity"]), (1, 8, "warning"))
        pr = checks.parse_pyright('{"generalDiagnostics": [{"file": "m.py", "severity": "error", "message": "bad", '
                                  '"range": {"start": {"line": 4, "character": 0}}, "rule": "reportGeneralTypeIssues"}]}', d, d)
        self.assertEqual((pr[0]["line"], pr[0]["col"]), (5, 1))                     # pyright counts from 0

    def test_mypy_flake8_and_compiler_lines(self):
        d = Path(self.root)
        my = checks.parse_mypy("m.py:3:5: error: Incompatible types  [assignment]\nm.py:3:5: note: see here\n", d, d)
        self.assertEqual(len(my), 1)
        self.assertEqual(my[0]["code"], "assignment")
        self.assertIn("see here", my[0]["message"])
        f8 = checks.parse_flake8("m.py:1:1: F401 'os' imported but unused\nm.py:2:1: E999 SyntaxError\n", d, d)
        self.assertEqual([x["severity"] for x in f8], ["warning", "error"])
        cargo = checks.parse_generic("src/main.rs:2:5: error[E0425]: cannot find value `y`\n"
                                     "warning: unused import\n", d, d, "cargo check")
        self.assertEqual((cargo[0]["file"], cargo[0]["code"], cargo[0]["line"]), ("src/main.rs", "E0425", 2))

    def test_python_syntax_needs_nothing_installed(self):
        self.write("ok.py", "x = 1\n")
        self.write("broken.py", "def f(:\n    pass\n")
        self.write("node_modules/skip.py", "def (\n")
        found = checks.python_syntax(Path(self.root), Path(self.root))
        self.assertEqual([(p["file"], p["line"]) for p in found], [("broken.py", 1)])

    def test_checkers_found_and_run(self):
        self.write("pyproject.toml", "[project]\nname='x'\n")
        self.write("bad.py", "if True\n")
        found = checks.detect(self.root)
        self.assertEqual([c["kind"] for c in found], ["pysyntax"])
        info = wait(projkit.start_job("p", self.root, lambda job: checks.run_checks(job, self.root, ["pysyntax:"]))["job"])
        r = info["result"]["results"][0]
        self.assertEqual(r["problems"][0]["file"], "bad.py")


# ---------------------------------------------------------------------------------------------------- tests
JUNIT = """<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" tests="3">
<testcase classname="tests.test_a.TestThing" name="test_ok" file="tests/test_a.py" line="4" time="0.01"/>
<testcase classname="tests.test_a" name="test_bad[1]" file="tests/test_a.py" line="9" time="0.20">
<failure message="assert 1 == 2">def test_bad(): assert 1 == 2</failure></testcase>
<testcase classname="tests.test_a" name="test_skip" file="tests/test_a.py" line="12" time="0"><skipped message="later"/></testcase>
</testsuite></testsuites>"""

UNITTEST_OUT = """test_a (tests.test_m.T.test_a) ... ok
test_b (tests.test_m.T.test_b)
The docstring line ... FAIL
test_c (tests.test_m.T.test_c) ... skipped 'not today'

======================================================================
FAIL: test_b (tests.test_m.T.test_b)
The docstring line
----------------------------------------------------------------------
Traceback (most recent call last):
  File "tests/test_m.py", line 7, in test_b
    self.assertEqual(1, 2)
AssertionError: 1 != 2

----------------------------------------------------------------------
Ran 3 tests in 0.001s

FAILED (failures=1, skipped=1)
"""


class Tests(Temp):
    def test_pytest_junit(self):
        t = testrun.parse_junit(JUNIT, Path(self.root), Path(self.root))
        self.assertEqual([x["id"] for x in t], ["tests/test_a.py::TestThing::test_ok", "tests/test_a.py::test_bad[1]",
                                                "tests/test_a.py::test_skip"])
        self.assertEqual([x["status"] for x in t], ["passed", "failed", "skipped"])
        self.assertEqual((t[1]["line"], t[1]["file"]), (10, "tests/test_a.py"))
        self.assertIn("assert 1 == 2", t[1]["message"])

    def test_unittest_lines(self):
        self.write("tests/test_m.py", "import unittest\nclass T(unittest.TestCase):\n    def test_a(self): pass\n"
                   "    def test_b(self):\n        'The docstring line'\n\n        self.assertEqual(1, 2)\n")
        t = {x["id"]: x for x in testrun.parse_unittest(UNITTEST_OUT, Path(self.root), Path(self.root))}
        self.assertEqual(t["tests.test_m.T.test_a"]["status"], "passed")
        self.assertEqual(t["tests.test_m.T.test_b"]["status"], "failed")
        self.assertIn("AssertionError: 1 != 2", t["tests.test_m.T.test_b"]["message"])
        self.assertEqual(t["tests.test_m.T.test_b"]["line"], 4)
        self.assertEqual(t["tests.test_m.T.test_c"]["status"], "skipped")

    def test_jest_vitest_go_cargo(self):
        d = Path(self.root)
        j = testrun.parse_jest_json({"testResults": [{"name": str(d / "a.test.ts"), "assertionResults": [
            {"fullName": "math adds", "title": "adds", "ancestorTitles": ["math"], "status": "failed",
             "failureMessages": ["\x1b[31mExpected 3\x1b[39m"], "duration": 5, "location": {"line": 3, "column": 2}}]}]}, d, d)
        self.assertEqual((j[0]["id"], j[0]["status"], j[0]["line"], j[0]["message"]), ("a.test.ts::math adds", "failed", 3, "Expected 3"))
        go = testrun.parse_go_json('{"Action":"run","Package":"ex/m","Test":"TestA"}\n'
                                   '{"Action":"output","Package":"ex/m","Test":"TestA","Output":"    m_test.go:9: boom\\n"}\n'
                                   '{"Action":"fail","Package":"ex/m","Test":"TestA","Elapsed":0.01}\n', d, d)
        self.assertEqual((go[0]["id"], go[0]["status"]), ("ex/m::TestA", "failed"))
        self.assertIn("boom", go[0]["message"])
        cargo = testrun.parse_cargo("test a::works ... ok\ntest a::breaks ... FAILED\n\nfailures:\n\n---- a::breaks stdout ----\n"
                                    "thread 'a::breaks' panicked at src/lib.rs:9:5:\nboom\n\nfailures:\n    a::breaks\n", d, d)
        self.assertEqual([c["status"] for c in cargo], ["passed", "failed"])
        self.assertIn("boom", cargo[1]["message"])

    def test_a_real_unittest_run_and_rerunning_only_the_failure(self):
        self.write("tests/__init__.py", "")
        self.write("tests/test_x.py", "import unittest\nclass X(unittest.TestCase):\n    def test_good(self):\n        pass\n"
                   "    def test_bad(self):\n        self.assertTrue(False)\n")
        with mock.patch.object(testrun, "_has_pytest", return_value=False):
            suites = testrun.detect(self.root, sys.executable)["suites"]
            self.assertEqual([s["kind"] for s in suites], ["unittest"])
            run = lambda only: wait(projkit.start_job("t", self.root, lambda job: testrun.run_tests(job, self.root, suites[0]["id"], sys.executable, only))["job"])
            info = run([])
            res = info["result"]
            self.assertEqual((res["summary"]["passed"], res["summary"]["failed"]), (1, 1), info["lines"])
            bad = next(t for t in res["tests"] if t["status"] == "failed")
            self.assertEqual((bad["file"], bad["line"]), ("tests/test_x.py", 5))
            again = run([bad["id"]])["result"]
            self.assertEqual(again["summary"]["total"], 1)

    def test_a_tests_folder_that_is_not_a_package(self):
        # like this repository: tests/ has no __init__.py, so its modules are top level ("test_y", not "tests.test_y")
        self.write("calc.py", "def two():\n    return 2\n")
        self.write("tests/test_y.py", "import unittest\nfrom calc import two\nclass Y(unittest.TestCase):\n    def test_two(self):\n"
                   "        self.assertEqual(two(), 2)\n    def test_three(self):\n        self.assertEqual(two(), 3)\n")
        with mock.patch.object(testrun, "_has_pytest", return_value=False):
            suite = testrun.detect(self.root, sys.executable)["suites"][0]["id"]
            run = lambda only: wait(projkit.start_job("t", self.root, lambda job: testrun.run_tests(job, self.root, suite, sys.executable, only))["job"])
            info = run([])
            res = info["result"]
            self.assertEqual((res["summary"]["passed"], res["summary"]["failed"]), (1, 1), info["lines"])
            bad = next(t for t in res["tests"] if t["status"] == "failed")
            self.assertEqual((bad["id"], bad["file"], bad["line"]), ("test_y.Y.test_three", "tests/test_y.py", 6))
            again = run([bad["id"]])["result"]
            self.assertEqual([t["id"] for t in again["tests"]], ["test_y.Y.test_three"])


# ---------------------------------------------------------------------------------------------------- http / ports
class _Echo(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/missing":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"nope")
            return
        if self.path == "/go":
            self.send_response(302)
            self.send_header("Location", "/json")
            self.end_headers()
            return
        body = json.dumps({"path": self.path, "ua": self.headers.get("User-Agent")}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n)
        self.send_response(201)
        self.send_header("Content-Type", self.headers.get("Content-Type") or "text/plain")
        self.end_headers()
        self.wfile.write(data)


class Net(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Echo)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_requests(self):
        base = f"http://127.0.0.1:{self.port}"
        r = netkit.send({"method": "GET", "url": base + "/json?a=1", "headers": [["X-Off", "1", False]]})
        self.assertEqual(r["status"], 200)
        self.assertEqual(json.loads(r["body"]), {"path": "/json?a=1", "ua": "Emilie-HTTP/1.0"})
        r = netkit.send({"method": "POST", "url": base + "/", "body": '{"a": 1}'})
        self.assertEqual((r["status"], r["body"]), (201, '{"a": 1}'))
        self.assertIn(["Content-Type", "application/json"], r["headers"])
        self.assertEqual(netkit.send({"url": base + "/missing"})["status"], 404)
        self.assertTrue(netkit.send({"url": base + "/go"})["redirected"])
        self.assertEqual(netkit.send({"url": base + "/go", "follow": False})["status"], 302)
        with self.assertRaises(ValueError):
            netkit.send({"url": "file:///etc/passwd"})

    def test_nothing_listening(self):
        s = __import__("socket").socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        r = netkit.send({"url": f"http://127.0.0.1:{port}/", "timeout": 3})
        self.assertIn("error", r)

    def test_our_test_server_is_listed_and_cannot_be_stopped_when_protected(self):
        rows = netkit.ports({os.getpid(): "this test"})["ports"]
        me = [r for r in rows if r["port"] == self.port]
        self.assertTrue(me, f"port {self.port} not in {[r['port'] for r in rows][:40]}")
        self.assertEqual(me[0]["pid"], os.getpid())
        self.assertEqual(me[0]["own"], "this test")
        self.assertTrue(me[0]["dev"])                       # Emilie's own (and any Python server) is listed by default
        with self.assertRaises(ValueError):
            netkit.kill(os.getpid(), {os.getpid(): "this test"})
        with self.assertRaises(ValueError):
            netkit.kill(4)


# ---------------------------------------------------------------------------------------------------- notes / database
class NotesAndDb(Temp):
    def test_notes_are_kept_outside_the_project(self):
        with mock.patch.object(notes, "NOTES", Path(self.root) / "notes-store"):
            self.assertEqual(notes.get(self.root)["text"], "")
            notes.save(self.root, "# plan\n- [ ] ship")
            self.assertEqual(notes.get(self.root)["text"], "# plan\n- [ ] ship")
            self.assertFalse(any(Path(self.root).glob("*.md")))

    def test_todo_comments(self):
        self.write("a.py", "x = 1  # TODO(ana): handle None\n# not a todo here\nprint('TODO in a string')\n")
        self.write("b.ts", "/* FIXME: slow */\n// HACK - temporary\n")
        self.write("node_modules/z.js", "// TODO hidden\n")
        found = {f["rel"]: f["items"] for f in notes.todos(self.root)["files"]}
        self.assertEqual(sorted(found), ["a.py", "b.ts"])
        self.assertEqual(found["a.py"], [{"line": 1, "tag": "TODO", "who": "ana", "text": "handle None"}])
        self.assertEqual([(i["tag"], i["text"]) for i in found["b.ts"]], [("FIXME", "slow"), ("HACK", "temporary")])

    def test_sqlite(self):
        db = Path(self.root) / "data" / "app.db"
        db.parent.mkdir()
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, avatar BLOB)")
        con.executemany("INSERT INTO users (name, avatar) VALUES (?, ?)", [("ana", b"\x00\x01"), ("budi", None)])
        con.commit()
        con.close()
        self.write("notes.db", "not sqlite")
        self.assertEqual([f["rel"] for f in sqlview.files(self.root)["files"]], ["data/app.db"])
        t = sqlview.tables(str(db))["tables"][0]
        self.assertEqual((t["name"], t["rows"], [c["name"] for c in t["columns"]]), ("users", 2, ["id", "name", "avatar"]))
        page = sqlview.browse(str(db), "users", order="name", desc=True)
        self.assertEqual(page["rows"][0][1], "budi")
        self.assertEqual(page["rows"][1][2], {"blob": 2})
        with self.assertRaises(ValueError):
            sqlview.browse(str(db), "users; drop table users")
        with self.assertRaises(ValueError):                       # read-only unless allowed
            sqlview.query(str(db), "DELETE FROM users")
        with self.assertRaises(ValueError):
            sqlview.query(str(db), "SELECT 1; SELECT 2")
        self.assertEqual(sqlview.query(str(db), "DELETE FROM users WHERE name = 'ana'", write=True)["changes"], 1)
        self.assertEqual(sqlview.query(str(db), "SELECT count(*) AS n FROM users")["rows"], [[1]])


if __name__ == "__main__":
    unittest.main()
