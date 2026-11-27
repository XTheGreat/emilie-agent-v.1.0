"""The HTTP and Ports panels.

HTTP: one request sent from here (not from the page, so there is no CORS and any local server can be reached), with
the response's status, headers, body and timing. Only http and https.

Ports: which TCP ports something listens on, and which process it is (to open a dev server, or stop the one that keeps
a port busy). Windows: netstat + tasklist; elsewhere lsof, else ss. A listening socket is recognised by its remote
address being 0 (language independent: Windows translates the word LISTENING)."""
from __future__ import annotations

import base64
import gzip
import os
import re
import shutil
import signal
import ssl
import time
import urllib.error
import urllib.request
import zlib
from urllib.parse import urlsplit

from .projkit import IS_WIN, run

MAX_BODY = 5_000_000
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send(b: dict) -> dict:
    method = str(b.get("method") or "GET").upper()
    if method not in METHODS:
        raise ValueError(f"unsupported method {method}")
    url = str(b.get("url") or "").strip()
    if re.match(r"^[a-z][a-z0-9+.-]*:/", url, re.I) and not re.match(r"^https?://", url, re.I):
        raise ValueError("Only http:// and https:// addresses can be sent.")
    if not re.match(r"^https?://", url, re.I):
        url = ("http://" if re.match(r"^(localhost|127\.|0\.0\.0\.0|\[::1\]|192\.168\.|10\.)", url) else "https://") + url
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        raise ValueError("Give a full http:// or https:// address.")
    headers: dict[str, str] = {}
    for h in b.get("headers") or []:
        if isinstance(h, (list, tuple)) and len(h) >= 2 and str(h[0]).strip():
            if len(h) >= 3 and h[2] is False:
                continue
            headers[str(h[0]).strip()] = str(h[1])
    if not any(k.lower() == "user-agent" for k in headers):
        headers["User-Agent"] = "Emilie-HTTP/1.0"
    body = b.get("body")
    data = None
    if body not in (None, "") and method not in ("GET", "HEAD"):
        data = str(body).encode("utf-8")
        if not any(k.lower() == "content-type" for k in headers):
            t = str(body).lstrip()[:1]
            headers["Content-Type"] = "application/json" if t in ("{", "[") else "text/plain; charset=utf-8"
    timeout = min(max(float(b.get("timeout") or 30), 1), 300)
    ctx = ssl._create_unverified_context() if b.get("insecure") else ssl.create_default_context()
    handlers: list = [urllib.request.HTTPSHandler(context=ctx)]
    host = (parts.hostname or "").lower()
    if host in ("localhost", "::1", "0.0.0.0") or host.startswith("127.") or host.endswith(".localhost"):
        handlers.append(urllib.request.ProxyHandler({}))        # a system proxy must not get the local dev server's traffic
    if not b.get("follow", True):
        handlers.append(_NoRedirect())
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    t0 = time.perf_counter()
    try:
        resp = opener.open(req, timeout=timeout)
        status, reason, final = resp.status, resp.reason, resp.geturl()
    except urllib.error.HTTPError as e:                 # 4xx / 5xx (and 3xx when not followed) still have a response
        resp, status, reason, final = e, e.code, e.reason, url
    except urllib.error.URLError as e:
        return {"error": _why(e.reason), "ms": round((time.perf_counter() - t0) * 1000)}
    except (TimeoutError, OSError, ValueError) as e:
        return {"error": _why(e), "ms": round((time.perf_counter() - t0) * 1000)}
    try:
        raw = resp.read(MAX_BODY + 1) if method != "HEAD" else b""
    except Exception as e:
        raw = b""
        reason = f"{reason} (body could not be read: {e})"
    finally:
        try:
            resp.close()
        except Exception:
            pass
    ms = round((time.perf_counter() - t0) * 1000)
    hdrs = [[k, v] for k, v in resp.headers.items()]
    cut = len(raw) > MAX_BODY
    raw = raw[:MAX_BODY]
    enc = (resp.headers.get("Content-Encoding") or "").lower()
    try:
        if enc == "gzip":
            raw = gzip.decompress(raw)
        elif enc == "deflate":
            raw = zlib.decompress(raw, -zlib.MAX_WBITS) if raw[:1] != b"\x78" else zlib.decompress(raw)
    except Exception:
        pass
    ctype = resp.headers.get("Content-Type") or ""
    out = {"status": status, "reason": str(reason or ""), "url": final, "redirected": final != url, "headers": hdrs,
           "ms": ms, "size": len(raw), "cut": cut, "type": ctype}
    if ctype.startswith("image/") and len(raw) < 3_000_000:
        out["image"] = f"data:{ctype.split(';')[0]};base64," + base64.b64encode(raw).decode()
        out["body"] = ""
    elif b"\x00" in raw[:4096] and not ctype.startswith("text/"):
        out["binary"] = True
        out["body"] = ""
    else:
        m = re.search(r"charset=([\w-]+)", ctype, re.I)
        try:
            out["body"] = raw.decode(m.group(1) if m else "utf-8", errors="replace")
        except LookupError:
            out["body"] = raw.decode("utf-8", errors="replace")
    return out


def _why(e) -> str:
    s = str(e)
    if isinstance(e, ConnectionRefusedError) or "refused" in s.lower() or "10061" in s:
        return "Connection refused: nothing is listening at that address (is the server running?)"
    if "timed out" in s.lower():
        return "The server did not answer in time."
    if "getaddrinfo" in s or "Name or service not known" in s or "11001" in s:
        return "That host name could not be found."
    if "CERTIFICATE_VERIFY_FAILED" in s:
        return "The server's certificate is not trusted (for a local dev server, turn on Allow self-signed certificates)."
    return s or type(e).__name__


# ---------------------------------------------------------------------------------------------------- ports
SYSTEM = {"system", "system idle process", "svchost.exe", "lsass.exe", "wininit.exe", "services.exe", "spoolsv.exe",
          "smss.exe", "csrss.exe", "winlogon.exe", "searchindexer.exe", "msedgewebview2.exe", "nvcontainer.exe",
          "jhi_service.exe", "lghub_agent.exe", "rapportd", "launchd", "systemd", "systemd-resolved", "sshd", "cupsd",
          "avahi-daemon", "controlcenter", "sharingd", "dnsmasq", "chronyd", "rpcbind", "mdnsresponder"}


def _windows() -> list[dict]:
    rows: dict[tuple, dict] = {}
    for proto in ("TCP", "TCPv6"):
        code, out = run(["netstat", "-ano", "-p", proto], os.getcwd(), 20)
        for line in out.splitlines():
            f = line.split()
            if len(f) < 5 or not f[0].upper().startswith("TCP"):
                continue
            local, remote, pid = f[1], f[2], f[-1]
            if not (remote.endswith(":0") or remote in ("*:*", "[::]:0")) or not pid.isdigit():
                continue
            addr, _, port = local.rpartition(":")
            if not port.isdigit():
                continue
            key = (int(port), int(pid))
            r = rows.setdefault(key, {"port": int(port), "pid": int(pid), "addresses": []})
            if addr not in r["addresses"]:
                r["addresses"].append(addr)
    names: dict[int, str] = {}
    code, out = run(["tasklist", "/FO", "CSV", "/NH"], os.getcwd(), 20)
    for line in out.splitlines():
        m = re.match(r'^"([^"]*)","(\d+)"', line)
        if m:
            names[int(m.group(2))] = m.group(1)
    for r in rows.values():
        r["name"] = names.get(r["pid"], "")
    return list(rows.values())


def _posix() -> list[dict]:
    rows: dict[tuple, dict] = {}
    if shutil.which("lsof"):
        code, out = run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-F", "pcn"], "/", 20)
        pid, name = 0, ""
        for line in out.splitlines():
            if line.startswith("p"):
                pid = int(line[1:]) if line[1:].isdigit() else 0
            elif line.startswith("c"):
                name = line[1:]
            elif line.startswith("n") and pid:
                addr, _, port = line[1:].rpartition(":")
                if port.isdigit():
                    r = rows.setdefault((int(port), pid), {"port": int(port), "pid": pid, "name": name, "addresses": []})
                    if addr not in r["addresses"]:
                        r["addresses"].append(addr)
    elif shutil.which("ss"):
        code, out = run(["ss", "-ltnpH"], "/", 20)
        for line in out.splitlines():
            f = line.split()
            if len(f) < 4:
                continue
            addr, _, port = f[3].rpartition(":")
            m = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
            pid = int(m.group(2)) if m else 0
            if port.isdigit():
                r = rows.setdefault((int(port), pid), {"port": int(port), "pid": pid, "name": m.group(1) if m else "", "addresses": []})
                if addr not in r["addresses"]:
                    r["addresses"].append(addr)
    return list(rows.values())


# What usually runs on a port while developing, and the programs that serve or store things for a project. Anything
# else (chat apps, game launchers, sync clients) is listed only with "All".
KNOWN = {
    3000: "React / Next / Express", 3001: "dev server", 4200: "Angular", 4321: "Astro", 5000: "Flask / dev server",
    5173: "Vite", 5174: "Vite", 5432: "PostgreSQL", 3306: "MySQL", 33060: "MySQL X", 6379: "Redis", 27017: "MongoDB",
    8000: "Django / FastAPI / http.server", 8080: "dev server", 8081: "dev server", 8888: "Jupyter", 9000: "dev server",
    1433: "SQL Server", 11434: "Ollama", 9229: "Node debugger", 4000: "dev server", 6006: "Storybook", 5500: "Live Server",
    1420: "Tauri", 19006: "Expo", 8787: "Wrangler", 5555: "Prisma Studio", 54321: "Supabase", 7700: "Meilisearch",
    9200: "Elasticsearch", 5672: "RabbitMQ", 15672: "RabbitMQ admin", 2375: "Docker", 4566: "LocalStack", 8025: "MailHog",
}
DEV_RANGES = ((3000, 3099), (4000, 4099), (4200, 4299), (5000, 5099), (5170, 5199), (8000, 8099), (8080, 8099))
DEV_NAMES = {
    "node", "python", "pythonw", "python3", "deno", "bun", "java", "javaw", "php", "php-cgi", "ruby", "dotnet", "go",
    "postgres", "mysqld", "mariadbd", "redis-server", "mongod", "nginx", "httpd", "caddy", "uvicorn", "gunicorn",
    "hypercorn", "docker", "dockerd", "com.docker.backend", "wslrelay", "vpnkit", "ngrok", "cloudflared", "beam.smp", "erl",
    "puma", "esbuild", "minio", "ollama", "jupyter", "jupyter-lab", "wrangler", "workerd", "meilisearch", "elasticsearch",
    "rabbitmq-server", "mailhog", "code", "cargo", "air", "hugo", "jekyll", "flutter", "dart",
}


def _base(name: str) -> str:
    n = (name or "").lower()
    return n[:-4] if n.endswith(".exe") else n


def ports(protect: dict[int, str] | None = None) -> dict:
    """[{port, pid, name, addresses, url, dev, own, hint, local}] sorted by port. protect: pid -> label (Emilie's own
    processes). dev: worth showing by default (see DEV_NAMES / KNOWN / DEV_RANGES)."""
    rows = _windows() if IS_WIN else _posix()
    protect = protect or {}
    for r in rows:
        name = _base(r.get("name") or "")
        port = r["port"]
        local = all(a in ("127.0.0.1", "[::1]", "::1", "localhost") for a in r["addresses"])
        r["url"] = f"http://localhost:{port}"
        r["own"] = protect.get(r["pid"], "")
        r["hint"] = KNOWN.get(port, "")
        system = r["pid"] <= 4 or (r.get("name") or "").lower() in SYSTEM
        r["dev"] = bool(r["own"]) or (not system and (name in DEV_NAMES or port in KNOWN or any(a <= port <= b for a, b in DEV_RANGES)))
        r["local"] = local
    rows.sort(key=lambda r: (r["port"], r["pid"]))
    return {"ports": rows, "at": time.time()}


def kill(pid: int, protect: dict[int, str] | None = None) -> dict:
    if pid <= 4:
        raise ValueError("That is a system process.")
    if protect and pid in protect:
        raise ValueError(f"That is {protect[pid]}: stopping it would close Emilie.")
    if IS_WIN:
        code, out = run(["taskkill", "/PID", str(pid), "/T", "/F"], os.getcwd(), 20)
        if code != 0:
            raise ValueError(out.strip() or "could not stop it")
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            raise ValueError("Not allowed to stop that process (it belongs to another user).")
    return {"ok": True}
