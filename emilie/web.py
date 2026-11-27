"""web_search and read_page: free or free-credit providers, spending as few tokens and credits as possible.

Search: Tavily / Exa / ddgs / SearXNG, chosen by intent. Reading: Jina Reader -> Firecrawl -> plain HTTP.
Results are cached in ./.cache/web/, monthly use per provider is counted in ~/.emilie/web_usage.json, and each task has
a small budget of calls. Everything that comes from the web is wrapped in <hasil_web> and is data, never instructions."""
import hashlib
import http.client
import ipaddress
import json
import logging
import os
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from . import paths

TIMEOUT = 20
INTENTS = ("news", "general", "semantic", "docs")
ROUTES = {"news": ("tavily", "ddgs", "searxng"), "general": ("tavily", "ddgs", "searxng"),
          "semantic": ("exa", "ddgs", "searxng"), "docs": ("ddgs", "searxng", "tavily")}
TTL = {"news": 30 * 60, "general": 24 * 3600, "semantic": 24 * 3600, "docs": 7 * 24 * 3600, "page": 24 * 3600}
KEYS = {"tavily": "TAVILY_API_KEY", "exa": "EXA_API_KEY", "firecrawl": "FIRECRAWL_API_KEY", "searxng": "SEARXNG_URL"}
SOFT_LIMITS = {"tavily": 900, "exa": 900, "firecrawl": 400}          # per month; <NAME>_LIMIT overrides
BUDGETS = {"search": ("WEB_SEARCH_BUDGET", 5), "read": ("WEB_READ_BUDGET", 3)}
SNIPPET, PAGE_CHARS, STORE_RESULTS = 300, 6000, 6
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) EmilieAgent/0.1"
BLOCKED_FILE = Path(__file__).resolve().parent.parent / "config" / "blocked_domains.txt"
USAGE_FILE = paths.HOME_DIR / "web_usage.json"
LOG_FILE = paths.HOME_DIR / "web.log"
TIME_SENSITIVE = re.compile(r"\b(latest|newest|today|current(ly)?|now|price|release[ds]?|schedule|status|version|"
                            r"terbaru|terkini|hari ini|sekarang|harga|jadwal|versi|rilis|20\d\d)\b", re.I)

_lock = threading.RLock()                # sub-agents search in parallel
_used = {"search": 0, "read": 0}

log = logging.getLogger("emilie.web")
log.propagate = False                    # printing would draw over the terminal screen


def _log(msg: str, *args) -> None:
    if not log.handlers:
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            h = logging.FileHandler(LOG_FILE, encoding="utf-8", delay=True)
            h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            log.addHandler(h)
            log.setLevel(logging.INFO)
        except OSError:
            log.addHandler(logging.NullHandler())
    log.info(msg, *args)


class ProviderError(Exception):
    """A short reason, safe to show: it never contains a key or a stack trace."""


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


# ------------------------------------------------------------------ budget and quota
def reset_budget() -> None:
    """Called at the start of every task (one user message)."""
    with _lock:
        _used.update(search=0, read=0)


def _spend(kind: str) -> bool:
    name, default = BUDGETS[kind]
    with _lock:
        if _used[kind] >= _env_int(name, default):
            return False
        _used[kind] += 1
        return True


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        _log("cannot write %s: %s", path.name, e)


def used(provider: str) -> int:
    return int(_read_json(USAGE_FILE).get(f"{date.today():%Y-%m}", {}).get(provider, 0))


def _count(provider: str, credits: int) -> None:
    with _lock:
        data = _read_json(USAGE_FILE)
        month = data.setdefault(f"{date.today():%Y-%m}", {})
        month[provider] = int(month.get(provider, 0)) + credits
        _write_json(USAGE_FILE, data)


def remaining(provider: str) -> int | None:
    if provider not in SOFT_LIMITS:
        return None
    return max(0, _env_int(f"{provider.upper()}_LIMIT", SOFT_LIMITS[provider]) - used(provider))


def _cost(provider: str) -> int:
    return 2 if provider == "tavily" and os.environ.get("TAVILY_DEPTH") == "advanced" else 1


# ------------------------------------------------------------------ cache
def _cache_file(key: str) -> Path:
    return Path.cwd() / ".cache" / "web" / (hashlib.sha256(key.encode()).hexdigest()[:32] + ".json")


def _cache_get(key: str, ttl: int):
    d = _read_json(_cache_file(key))
    return d.get("value") if d.get("key") == key and time.time() - d.get("at", 0) < ttl else None


def _cache_put(key: str, value) -> None:
    f = _cache_file(key)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        ignore = f.parent.parent / ".gitignore"
        if not ignore.exists():
            ignore.write_text("*\n", encoding="utf-8")       # never commit the cache of the user's project
    except OSError:
        return
    _write_json(f, {"key": key, "at": time.time(), "value": value})


# ------------------------------------------------------------------ HTTP
def _reason(e: Exception) -> str:
    if isinstance(e, urllib.error.HTTPError):
        if e.code in (402, 429, 432, 433):
            return f"kuota habis atau dibatasi (HTTP {e.code})"
        if e.code in (401, 403):
            return f"ditolak, periksa API key atau akses (HTTP {e.code})"
        return f"HTTP {e.code}"
    s = str(getattr(e, "reason", e))
    if "Hostname mismatch" in s:
        return "jaringan membelokkan alamat ini (blokir ISP atau halaman login)"
    if isinstance(e, TimeoutError) or "timed out" in s:
        return "timeout"
    return s[:120] or type(e).__name__


def _transient(e: Exception) -> bool:
    """Worth one more try: a network hiccup or a gateway error. Never a 4xx or a certificate problem."""
    if isinstance(e, urllib.error.HTTPError):
        return e.code in (502, 503, 504)
    if isinstance(e, ssl.SSLCertVerificationError) or isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
        return False
    return isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException))


def _http(url: str, body: dict | None = None, headers: dict | None = None, opener=None) -> tuple[str, str]:
    """-> (text, content type). A body makes it a JSON POST."""
    h = {"User-Agent": USER_AGENT, **(headers or {})}
    data = None
    if body is not None:
        data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
    send = opener.open if opener else urllib.request.urlopen
    for attempt in (1, 2):
        try:
            with send(urllib.request.Request(url, data=data, headers=h), timeout=TIMEOUT) as r:
                ctype = r.headers.get("Content-Type", "")
                charset = r.headers.get_content_charset() or "utf-8"
                raw = r.read(2_000_000)
            try:
                return raw.decode(charset, errors="replace"), ctype
            except LookupError:
                return raw.decode("utf-8", errors="replace"), ctype
        except (OSError, http.client.HTTPException) as e:
            if attempt == 1 and _transient(e):
                continue
            raise ProviderError(_reason(e)) from None
        except ValueError as e:
            raise ProviderError(str(e)[:120]) from None


def _http_json(url: str, body: dict | None = None, headers: dict | None = None) -> dict:
    text, _ = _http(url, body, headers)
    try:
        return json.loads(text)
    except ValueError:
        raise ProviderError("jawaban bukan JSON") from None


# ------------------------------------------------------------------ search providers
def _tavily(query: str, intent: str) -> list[dict]:
    body = {"query": query, "max_results": STORE_RESULTS, "include_raw_content": False,
            "search_depth": "advanced" if os.environ.get("TAVILY_DEPTH") == "advanced" else "basic"}
    if intent == "news":
        body.update(topic="news", days=3)
    elif intent == "general" and TIME_SENSITIVE.search(query):
        body["time_range"] = "month"
    d = _http_json("https://api.tavily.com/search", body,
                   {"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"})
    return [{"title": r.get("title"), "url": r.get("url"), "date": r.get("published_date"),
             "snippet": r.get("content")} for r in d.get("results") or []]


def _exa(query: str, intent: str) -> list[dict]:
    d = _http_json("https://api.exa.ai/search",
                   {"query": query, "numResults": STORE_RESULTS, "type": "auto",
                    "contents": {"highlights": {"maxCharacters": SNIPPET}}},
                   {"x-api-key": os.environ["EXA_API_KEY"]})
    return [{"title": r.get("title"), "url": r.get("url"), "date": r.get("publishedDate"),
             "snippet": " ".join(r.get("highlights") or []) or r.get("text")} for r in d.get("results") or []]


def _ddgs_class():
    try:
        from ddgs import DDGS
    except ImportError:
        return None
    return DDGS


def _ddgs(query: str, intent: str) -> list[dict]:
    try:
        client = _ddgs_class()(timeout=TIMEOUT)
        rows = (client.news if intent == "news" else client.text)(query, max_results=STORE_RESULTS)
    except Exception as e:              # the library raises its own types
        raise ProviderError(f"{type(e).__name__}: {str(e)[:80]}") from None
    return [{"title": r.get("title"), "url": r.get("href") or r.get("url"), "date": r.get("date"),
             "snippet": r.get("body")} for r in rows or []]


def _searxng(query: str, intent: str) -> list[dict]:
    q = {"q": query, "format": "json"}
    if intent == "news":
        q["categories"] = "news"
    d = _http_json(os.environ["SEARXNG_URL"].rstrip("/") + "/search?" + urlencode(q))
    return [{"title": r.get("title"), "url": r.get("url"), "date": r.get("publishedDate"),
             "snippet": r.get("content")} for r in d.get("results") or []]


SEARCHERS = {"tavily": _tavily, "exa": _exa, "ddgs": _ddgs, "searxng": _searxng}


def _unavailable(provider: str) -> str:
    """Why a provider is skipped without being tried ("" = usable)."""
    if provider == "ddgs":
        return "" if _ddgs_class() else "paket ddgs belum terpasang (pip install ddgs)"
    if provider in KEYS and not os.environ.get(KEYS[provider], "").strip():
        return f"{KEYS[provider]} belum diisi"
    left = remaining(provider)
    if left is not None and left < _cost(provider):
        return "batas bulanan tercapai"
    return ""


# ------------------------------------------------------------------ cleaning
def normalize_url(url: str) -> str:
    p = urlsplit(url.strip())
    host = p.netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid", "mc_cid", "mc_eid")]
    return urlunsplit((p.scheme.lower(), host, p.path.rstrip("/"), urlencode(query), ""))


def _blocked_domains() -> set[str]:
    try:
        lines = BLOCKED_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    return {x.split("#")[0].strip().lower() for x in lines} - {""}


def _blocked(host: str, blocked: set[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in blocked)


def _date(value) -> str:
    s = str(value or "").strip()
    if re.match(r"\d{4}-\d\d-\d\d", s):
        return s[:10]
    try:
        return f"{parsedate_to_datetime(s):%Y-%m-%d}"
    except (TypeError, ValueError, IndexError):
        return s[:25]


def _one_line(s, limit: int) -> str:
    s = " ".join(re.sub(r"<[^>]+>", " ", str(s or "")).split())
    return s if len(s) <= limit else s[:limit - 1].rstrip() + "…"


def _clean_results(rows: list[dict]) -> list[dict]:
    blocked, seen, out = _blocked_domains(), set(), []
    for r in rows:
        url = str(r.get("url") or "").strip()
        if urlsplit(url).scheme not in ("http", "https") or any(c.isspace() for c in url):
            continue
        key = normalize_url(url)
        host = urlsplit(key).hostname or ""
        if key in seen or _blocked(host, blocked):
            continue
        seen.add(key)
        out.append({"title": _one_line(r.get("title") or host, 150), "url": url.split("#")[0], "domain": host,
                    "date": _date(r.get("date")), "snippet": _one_line(r.get("snippet"), SNIPPET)})
    return out


def _wrap(body: str) -> str:
    body = re.sub(r"<(/?)\s*hasil_web", r"‹\1hasil_web", body, flags=re.I)      # a page cannot close the wrapper
    return f"<hasil_web>\n{body}\n</hasil_web>"


# ------------------------------------------------------------------ web_search
def web_search(query: str, intent: str = "general", max_results: int = 4) -> str:
    query = " ".join(str(query or "").split())
    if not query:
        return "ERROR: empty query"
    intent = intent if intent in INTENTS else "general"
    try:
        n = max(1, min(int(max_results), STORE_RESULTS))
    except (TypeError, ValueError):
        n = 4
    key = f"search|{intent}|{query.lower()}"
    rows, cached, provider = _cache_get(key, TTL[intent]), True, "cache"
    if rows is None:
        cached = False
        if not _spend("search"):
            return "ERROR: anggaran pencarian habis, jawab dengan informasi yang ada"
        problems, tried = [], 0
        for provider in ROUTES[intent]:
            why = _unavailable(provider)
            if why:
                if provider != "searxng":                 # optional: its absence is not a problem
                    problems.append(f"{provider}: {why}")
                continue
            if tried == 2:
                break
            tried += 1
            try:
                found = SEARCHERS[provider](query, intent)
            except ProviderError as e:
                problems.append(f"{provider}: {e}")
                _log("search %s gagal (%s), turun ke provider berikutnya", provider, e)
                continue
            if provider in SOFT_LIMITS:
                _count(provider, _cost(provider))
            rows = _clean_results(found)
            if rows:
                break
            problems.append(f"{provider}: tidak ada hasil")
        if rows is None:
            _log("search gagal: %s", "; ".join(problems))
            return "ERROR: pencarian gagal (" + "; ".join(problems) + "). Jangan ulangi pencarian yang sama."
        if not rows:
            return "tidak ada hasil untuk pencarian ini"
        _cache_put(key, rows)
    blocked = _blocked_domains()
    rows = [r for r in rows if not _blocked(r["domain"], blocked)][:n]
    lines = []
    for i, r in enumerate(rows, 1):
        head = " | ".join(x for x in (r["title"], r["domain"], r["date"]) if x)
        lines.append(f"[{i}] {head}\n    {r['snippet']}\n    {r['url']}" if r["snippet"] else
                     f"[{i}] {head}\n    {r['url']}")
    out = ("(dari cache)\n" if cached else "") + _wrap("\n".join(lines) or "tidak ada hasil")
    _log("web_search intent=%s provider=%s hasil=%d sisa_kuota=%s token~%d", intent, provider, len(rows),
         remaining(provider), len(out) // 4)
    return out


# ------------------------------------------------------------------ read_page
def check_url(url: str) -> str:
    """"" when the URL is a public http(s) address, else why not (SSRF protection)."""
    try:
        p = urlsplit(url)
        port = p.port
    except ValueError:
        return "URL tidak valid"
    if p.scheme not in ("http", "https") or not p.hostname:
        return "hanya URL http/https"
    if p.username or p.password:
        return "URL berisi nama pengguna/kata sandi tidak diizinkan"
    host = p.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return "alamat lokal/privat ditolak"
    try:
        infos = socket.getaddrinfo(host, port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return "nama host tidak ditemukan"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global or ip.is_multicast:
            return "alamat lokal/privat ditolak"
    return ""


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        why = check_url(newurl)
        if why:
            raise ValueError(f"redirect ditolak: {why}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _Markdown(HTMLParser):
    """Readable text of a page, without menus, forms and footers."""
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "aside", "form", "button", "iframe",
            "template", "select"}
    BLOCK = {"p", "div", "section", "article", "tr", "ul", "ol", "table", "blockquote"}

    def __init__(self):
        super().__init__()
        self.out, self.depth, self.pre = [], 0, False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
        elif self.depth:
            return
        elif tag == "pre":
            self.pre = True
            self.out.append("\n\n```\n")
        elif re.fullmatch(r"h[1-6]", tag):
            self.out.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag == "br":
            self.out.append("\n")
        elif tag in self.BLOCK:
            self.out.append("\n\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.depth = max(0, self.depth - 1)
        elif tag == "pre" and self.pre:
            self.pre = False
            self.out.append("\n```\n\n")
        elif not self.depth and (tag in self.BLOCK or re.fullmatch(r"h[1-6]", tag)):
            self.out.append("\n\n")

    def handle_data(self, data):
        if not self.depth:
            self.out.append(data if self.pre else re.sub(r"\s+", " ", data))


def _jina(url: str) -> str:
    headers = {"Accept": "text/plain"}
    key = os.environ.get("JINA_API_KEY", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return _http("https://r.jina.ai/" + quote(url, safe=":/?&=%+,;@-._~!$'()*"), headers=headers)[0]


def _firecrawl(url: str) -> str:
    d = _http_json("https://api.firecrawl.dev/v2/scrape",
                   {"url": url, "formats": ["markdown"], "onlyMainContent": True},
                   {"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"})
    return str((d.get("data") or {}).get("markdown") or "")


def _direct(url: str) -> str:
    text, ctype = _http(url, opener=urllib.request.build_opener(_SafeRedirect))
    ctype = ctype.lower()
    if ctype and not any(t in ctype for t in ("text", "json", "xml", "html")):
        raise ProviderError(f"bukan halaman teks ({ctype.split(';')[0]})")
    if "html" in ctype or text.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        p = _Markdown()
        p.feed(text)
        text = "".join(p.out)
    return text


READERS = {"jina": _jina, "firecrawl": _firecrawl, "direct": _direct}
BOILERPLATE = re.compile(r"cookie|accept all|subscribe|sign in|log in|newsletter|all rights reserved|privacy policy|"
                         r"skip to (main )?content|kebijakan privasi|berlangganan", re.I)


def clean_text(text: str) -> str:
    out, blank, code = [], False, False
    for line in text.replace("\r", "").split("\n"):
        fence = line.lstrip().startswith("```")
        if code or fence:                                             # code keeps its indentation and blank lines
            if blank:
                out.append("")
                blank = False
            out.append(line.rstrip())
            code = code != fence
            continue
        line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)              # images cost tokens and show nothing
        line = re.sub(r"[ \t ]+", " ", line).strip()
        bare = re.sub(r"\[[^\]]*\]\([^)]*\)", "", line).strip(" -*|•>#")
        if line and not bare and "](" in line:                        # only links: keep headlines, drop menus
            titles = [t.strip() for t in re.findall(r"\[([^\]]*)\]\(", line) if len(t.strip()) >= 30]
            line = "- " + " · ".join(titles) if titles else ""
            if not line:
                continue
        if len(line) < 100 and BOILERPLATE.search(line):
            continue                                                  # a banner, a footer
        if not line:
            blank = bool(out)
            continue
        if blank:
            out.append("")
            blank = False
        out.append(line)
    return "\n".join(out)


def excerpt(text: str, focus: str = "", limit: int = PAGE_CHARS) -> str:
    if len(text) <= limit:
        return text
    words = {w for w in re.findall(r"\w{3,}", (focus or "").lower())}
    if words:
        paras = [p for p in text.split("\n\n") if p.strip()]

        def score(p: str) -> tuple[int, int]:
            low = p.lower()
            return sum(w in low for w in words), sum(low.count(w) for w in words)

        ranked = sorted(paras, key=score, reverse=True)               # stable: ties keep the page's order
        body = "\n\n".join(ranked)[:limit]
    else:
        body = text[:limit]
    return f"{body.rstrip()}\n[dipotong, total {len(text)} karakter]"


def read_page(url: str, focus: str = "") -> str:
    url = str(url or "").strip().split("#")[0]
    why = check_url(url)
    if why:
        return f"ERROR: {why}"
    key = "page|" + normalize_url(url)
    text, cached, provider = _cache_get(key, TTL["page"]), True, "cache"
    if text is None:
        cached = False
        if not _spend("read"):
            return "ERROR: anggaran pencarian habis, jawab dengan informasi yang ada"
        problems = []
        for provider, reader in READERS.items():
            if provider == "firecrawl" and _unavailable(provider):
                continue
            try:
                found = reader(url)
            except ProviderError as e:
                problems.append(f"{provider}: {e}")
                _log("read %s gagal (%s), turun ke pembaca berikutnya", provider, e)
                continue
            if provider in SOFT_LIMITS:
                _count(provider, 1)
            text = clean_text(found)
            if text:
                break
            problems.append(f"{provider}: halaman kosong")
        if not text:
            return "ERROR: halaman tidak bisa dibaca (" + "; ".join(problems) + ")"
        _cache_put(key, text)
    out = ("(dari cache)\n" if cached else "") + _wrap(excerpt(text, focus))
    _log("read_page provider=%s sisa_kuota=%s token~%d", provider, remaining(provider), len(out) // 4)
    return out


def today_note() -> str:
    return f"Today's date: {datetime.now():%Y-%m-%d} (use it to judge how fresh a web source is)."
