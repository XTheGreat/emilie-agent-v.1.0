"""is_readonly_cmd must not auto-allow commands that run other code. Commands are only classified, never run."""
import tempfile
import unittest
from unittest import mock

from emilie import policy

BOTH = [
    "write-output (set-content x.txt hi)",
    "echo (ni x.txt)",
    "ls (ni x.txt)",
    "echo @(ni x.txt)",
    "echo $(ni x.txt)",
    "ls & touch x",
    "ls\rtouch x",
    "cat <(touch x)",
    "(touch x)",
]
WINDOWS = BOTH + [
    "gci | where { ni x }",
    "ls | sort {ni x}",
    "echo @{a=ni x}",
    'echo "a\\" (ni x) "',                     # backslash does not escape a quote in PowerShell
    "echo \\(ni x)",
    "echo 'a\u2019 (ni x) '",                  # a curly quote closes a PowerShell string
    "& ni x",
]
POSIX = BOTH + ["echo $'\\'' & touch x #'", 'echo \\\\"a" (touch x)']

OK_BOTH = [
    "ls -la", "git status", "git log --oneline | head -5", "cat a.txt && ls", "ls 2>&1",
    'grep "foo(" a.py', "rg 'def \\w+\\(' src", 'echo "a & b {c}"', "echo ${HOME}", "python --version",
]
OK_WINDOWS = ["get-childitem -Recurse","gc 'C:\\Program Files (x86)\\a.txt'", "echo ${env:PATH}",
              "gci | where Name -eq x", "dir C:\\temp | measure-object"]
OK_POSIX = ["find . \\( -name a -o -name b \\)", "ls *.{js,ts}", "echo a\\&b", "cat /tmp/a\\ \\(1\\).txt"]


class PolicyReadonlyTest(unittest.TestCase):
    def check(self, windows, bad, good):
        with mock.patch.object(policy, "IS_WIN", windows), \
             mock.patch.object(policy.Policy, "_rules", staticmethod(lambda kind: [])), \
             tempfile.TemporaryDirectory() as ws:
            p = policy.Policy(ws)
            for cmd in bad:
                for tool in ("bash", "bash_bg"):
                    with self.subTest(cmd=cmd, tool=tool):
                        p.mode = "ask"
                        self.assertEqual(p.check(tool, {"command": cmd})[0], "ask")
                        p.mode = "plan"
                        self.assertEqual(p.check(tool, {"command": cmd})[0], "deny")
            for cmd in good:
                with self.subTest(cmd=cmd):
                    self.assertTrue(policy.is_readonly_cmd(cmd))

    def test_powershell(self):
        self.check(True, WINDOWS, OK_BOTH + OK_WINDOWS)

    def test_posix(self):
        self.check(False, POSIX, OK_BOTH + OK_POSIX)


if __name__ == "__main__":
    unittest.main()
