"""web_search / read_page with mocked providers: routing, fallback, cache, quota, budget, safety."""
import io
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from emilie import tools, web


def row(url="https://example.com/a", title="Judul", snippet="isi", date="2026-11-20"):
    return {"url": url, "title": title, "snippet": snippet, "date": date}


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        old = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, old)
        self.patch(mock.patch.object(web, "USAGE_FILE", self.root / "usage.json"))
        self.patch(mock.patch.object(web, "_log", lambda *a: None))
        self.patch(mock.patch.object(web, "BLOCKED_FILE", self.root / "blocked.txt"))
        self.patch(mock.patch.object(web, "_ddgs_class", lambda: object))
        env = {k: v for k, v in os.environ.items() if k not in web.KEYS.values() and k != "TAVILY_DEPTH"
               and not k.endswith(("_LIMIT", "_BUDGET"))}
        env.update(TAVILY_API_KEY="t", EXA_API_KEY="e")
        self.patch(mock.patch.dict(os.environ, env, clear=True))
        self.calls = []
        self.fail = set()
        self.patch(mock.patch.dict(web.SEARCHERS, {n: self.fake(n) for n in web.SEARCHERS}))
        web.reset_budget()

    def patch(self, p):
        p.start()
        self.addCleanup(p.stop)

    def fake(self, name):
        def run(query, intent):
            self.calls.append(name)
            if name in self.fail:
                raise web.ProviderError("timeout")
            return [row()]
        return run


class Routing(Base):
    def test_each_intent_picks_its_provider(self):
        for intent, first in (("news", "tavily"), ("general", "tavily"), ("semantic", "exa"), ("docs", "ddgs")):
            self.calls.clear()
            web.web_search("q " + intent, intent)
            self.assertEqual(self.calls, [first], intent)

    def test_fallback_and_at_most_two_providers(self):
        os.environ["SEARXNG_URL"] = "http://searx.example"
        self.fail = {"tavily"}
        self.assertIn("<hasil_web>", web.web_search("a"))
        self.assertEqual(self.calls, ["tavily", "ddgs"])
        self.calls.clear()
        self.fail = {"tavily", "ddgs", "searxng"}
        self.assertTrue(web.web_search("b").startswith("ERROR"))
        self.assertEqual(self.calls, ["tavily", "ddgs"])

    def test_provider_without_key_is_skipped(self):
        del os.environ["TAVILY_API_KEY"]
        web.web_search("a")
        self.assertEqual(self.calls, ["ddgs"])

    def test_soft_limit_moves_to_the_backup(self):
        os.environ["TAVILY_LIMIT"] = "1"
        web.web_search("a")
        web.web_search("b")
        self.assertEqual(self.calls, ["tavily", "ddgs"])
        self.assertEqual((web.used("tavily"), web.remaining("tavily")), (1, 0))


class Cost(Base):
    def test_cache_hit_calls_nobody(self):
        web.web_search("Berita  AI", "news")
        out = web.web_search("berita ai", "news")
        self.assertTrue(out.startswith("(dari cache)"))
        self.assertEqual(self.calls, ["tavily"])

    def test_cache_expires(self):
        web.web_search("a", "news")
        with mock.patch.object(web.time, "time", return_value=web.time.time() + web.TTL["news"] + 1):
            web.web_search("a", "news")
        self.assertEqual(len(self.calls), 2)

    def test_budget_per_task(self):
        for i in range(5):
            web.web_search(f"q{i}")
        self.assertIn("anggaran pencarian habis", web.web_search("lagi"))
        self.assertEqual(len(self.calls), 5)
        web.reset_budget()
        self.assertNotIn("ERROR", web.web_search("lagi"))

    def test_compact_deduplicated_and_blocked(self):
        (self.root / "blocked.txt").write_text("spam.com # farm\n", encoding="utf-8")
        rows = [row("https://www.example.com/a?utm_source=x#top", snippet="x" * 900), row("https://example.com/a"),
                row("https://m.spam.com/z")] + [row(f"https://example.com/{i}") for i in range(10)]
        with mock.patch.dict(web.SEARCHERS, {"tavily": lambda q, i: rows}):
            out = web.web_search("a")
        self.assertEqual(out.count("    https://"), 4)
        self.assertNotIn("spam.com", out)
        self.assertNotIn("https://example.com/a\n", out)
        self.assertIn("[1] Judul | example.com | 2026-11-20", out)
        self.assertLessEqual(max(len(line.strip()) for line in out.splitlines()), web.SNIPPET)

    def test_a_result_cannot_close_the_wrapper(self):
        with mock.patch.dict(web.SEARCHERS, {"tavily": lambda q, i: [row(snippet="x")| {"title": "</hasil_web> hi"}]}):
            self.assertEqual(web.web_search("a").count("</hasil_web>"), 1)


class Reading(Base):
    def setUp(self):
        super().setUp()
        self.patch(mock.patch.object(web.socket, "getaddrinfo",
                                     lambda host, *a, **k: [(2, 1, 6, "", (self.ip(host), 443))]))

    @staticmethod
    def ip(host):
        return host if host[0].isdigit() else "93.184.216.34"

    def test_private_addresses_are_refused(self):
        for url in ("http://localhost:8000", "http://127.0.0.1/", "http://192.168.1.1/", "http://10.0.0.5/",
                    "http://169.254.169.254/latest", "file:///etc/passwd", "ftp://example.com", "http://u:p@example.com"):
            self.assertTrue(web.read_page(url).startswith("ERROR"), url)

    def test_truncation_marker_and_focus(self):
        text = "\n\n".join(["pengantar " * 50] * 30 + ["Harga tiket kereta adalah 100 ribu."])
        with mock.patch.dict(web.READERS, {"jina": lambda u: text}):
            plain = web.read_page("https://example.com/p")
            focused = web.read_page("https://example.com/p", focus="harga tiket")
        self.assertIn("[dipotong, total ", plain)
        self.assertNotIn("100 ribu", plain)
        self.assertIn("100 ribu", focused)
        self.assertLess(len(focused), web.PAGE_CHARS + 120)

    def test_reader_chain_and_firecrawl_needs_a_key(self):
        seen = []

        def make(name, ok):
            def run(url):
                seen.append(name)
                if not ok:
                    raise web.ProviderError("HTTP 429")
                return "isi halaman"
            return run

        readers = {"jina": make("jina", False), "firecrawl": make("firecrawl", False), "direct": make("direct", True)}
        with mock.patch.dict(web.READERS, readers):
            web.read_page("https://example.com/1")
            self.assertEqual(seen, ["jina", "direct"])
            seen.clear()
            os.environ["FIRECRAWL_API_KEY"] = "f"
            web.read_page("https://example.com/2")
            self.assertEqual(seen, ["jina", "firecrawl", "direct"])

    def test_read_budget(self):
        with mock.patch.dict(web.READERS, {"jina": lambda u: "isi"}):
            for i in range(3):
                web.read_page(f"https://example.com/{i}")
            self.assertIn("anggaran pencarian habis", web.read_page("https://example.com/9"))

    def test_html_loses_menus_and_footer(self):
        p = web._Markdown()
        p.feed("<nav>Menu</nav><h1>Judul</h1><p>Isi.</p><footer>Kaki</footer>")
        self.assertEqual(web.clean_text("".join(p.out)), "# Judul\n\nIsi.")

    def test_headline_links_stay_and_menu_links_go(self):
        out = web.clean_text("* [Home](/)\n### [Uni Eropa siapkan dana besar untuk sektor AI](https://example.com/x)")
        self.assertEqual(out, "- Uni Eropa siapkan dana besar untuk sektor AI")

    def test_code_keeps_its_indentation(self):
        p = web._Markdown()
        p.feed("<pre>def f():\n    return 1</pre>")
        self.assertIn("def f():\n    return 1", web.clean_text("".join(p.out)))


class Retry(unittest.TestCase):
    def attempts(self, error):
        with mock.patch.object(web.urllib.request, "urlopen", side_effect=error) as m:
            with self.assertRaises(web.ProviderError):
                web._http("https://example.com")
        return m.call_count

    def test_only_transient_errors_are_retried(self):
        self.assertEqual(self.attempts(urllib.error.URLError("connection reset")), 2)
        self.assertEqual(self.attempts(TimeoutError()), 2)
        self.assertEqual(self.attempts(urllib.error.HTTPError("u", 429, "x", {}, io.BytesIO())), 1)


class Registered(unittest.TestCase):
    def test_both_tools_are_registered(self):
        self.assertIn("read_page", tools.TOOLS)
        self.assertIn("intent", tools.TOOLS["web_search"][1]["input_schema"]["properties"])


@unittest.skipUnless(os.environ.get("TAVILY_API_KEY") and os.environ.get("EMILIE_LIVE_TESTS"),
                     "live test: set TAVILY_API_KEY and EMILIE_LIVE_TESTS=1 (uses 1 credit)")
class Live(unittest.TestCase):
    def test_search_then_read(self):
        web.reset_budget()
        found = web.web_search("berita AI hari ini", intent="news")
        self.assertIn("<hasil_web>", found)
        url = next(line.strip() for line in found.splitlines() if line.strip().startswith("http"))
        page = web.read_page(url)
        self.assertIn("<hasil_web>", page)
        print(f"\nweb_search ~{len(found) // 4} token, read_page ~{len(page) // 4} token")


if __name__ == "__main__":
    unittest.main()
