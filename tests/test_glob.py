"""glob with sort="size": what lets a read-only sub-agent find the largest files."""
import tempfile
import unittest
from pathlib import Path

from emilie import tools
from emilie.agent import Agent


class GlobBySize(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        for name, size in (("small.rs", 10), ("big.rs", 5000), ("mid.rs", 300), ("other.txt", 9999)):
            (Path(self.root) / name).write_bytes(b"x" * size)

    def test_largest_first_with_sizes(self):
        lines = tools.invoke("glob", {"pattern": "*.rs", "path": self.root, "sort": "size"}).splitlines()
        self.assertEqual([Path(l.split("  (")[0]).name for l in lines], ["big.rs", "mid.rs", "small.rs"])
        self.assertIn("(5,000 bytes)", lines[0])

    def test_default_output_unchanged(self):
        out = tools.invoke("glob", {"pattern": "*.rs", "path": self.root})
        self.assertNotIn("bytes", out)
        self.assertEqual(len(out.splitlines()), 3)

    def test_sub_agent_can_use_it_but_cannot_run_commands(self):
        self.assertIn("glob", Agent.SUB_TOOLS)
        self.assertNotIn("bash", Agent.SUB_TOOLS)
        self.assertIn('sort="size"', Agent.SUB_SYSTEM)


if __name__ == "__main__":
    unittest.main()
