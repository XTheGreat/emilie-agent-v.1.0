#!/usr/bin/env python3
"""Check how a codebase talks to outside services: timeouts, TLS, secrets, webhooks, retries.

Usage: python integration_check.py [path] [--json]

Looks for (read-only, stdlib only):
  * Outbound HTTP calls with no timeout: Python requests / urllib, JS axios /
    fetch (no AbortSignal), Go net/http default client.
  * TLS verification turned off (verify=False, rejectUnauthorized: false,
    InsecureSkipVerify), plain http:// URLs to non-local hosts.
  * Secrets that look real (provider key formats, private keys, hard-coded
    api_key/secret/password/token assignments). Values are MASKED in the output.
  * Webhook handlers whose file never mentions signature/HMAC verification.
  * Whether retry/backoff logic exists anywhere, and whether .env is ignored
    and .env.example exists.

Findings are leads: confirm in the code. Textual search only - it cannot see
timeouts set on a shared client/session, config-driven URLs, or secrets in
git history (check those with `git log -S`).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist", "build", "out", ".next", "target", "vendor", "site-packages", "coverage", ".tox", ".idea", ".vscode"}
CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".java", ".kt", ".rb", ".php", ".cs", ".rs", ".swift", ".sh", ".ps1", ".yaml", ".yml", ".json", ".toml", ".env", ".cfg", ".ini", ".properties", ".tf"}
TEST_RX = re.compile(r"(^|/)(tests?|__tests__|spec|fixtures?|examples?|docs?)(/|$)|\.(test|spec)\.|_test\.|test_[^/]*\.py$", re.I)

SECRET_FORMATS = [
    ("AWS access key id", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("Stripe live key", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{16,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b")),
    ("Anthropic-style key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
]
ASSIGN = re.compile(r"""(?ix)\b([A-Za-z_]*(?:api[_-]?key|secret|passwd|password|token|private[_-]?key|client[_-]?secret|auth)[A-Za-z_]*)\s*[:=]\s*['"]([^'"\s]{8,})['"]""")
PLACEHOLDER = re.compile(r"(?i)^(x+|\*+|<.*>|\$\{.*\}|\{\{.*\}\}|your[_-].*|change[_-]?me|example.*|placeholder|dummy|test.*|todo|none|null|env\(.*|process\.env.*|os\.environ.*|%\(.*|.*_here|.*\.\.\.)$")


def mask(v: str) -> str:
    return v[:4] + "*" * min(8, max(len(v) - 4, 0)) + f" (len {len(v)})"


def call_text(text: str, start: int) -> str:
    """Text of a call from the opening paren at/after `start` to its matching close (bounded)."""
    i = text.find("(", start)
    if i < 0:
        return ""
    depth, j = 0, i
    while j < len(text) and j - i < 1500:
        c = text[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[i : j + 1]
        j += 1
    return text[i : j]


def check_file(rel: str, text: str, ext: str, findings: list, flags: dict):
    def add(sev, line, msg, why):
        findings.append({"severity": sev, "where": f"{rel}:{line}", "finding": msg, "why": why})

    lineno = lambda pos: text.count("\n", 0, pos) + 1  # noqa: E731
    is_test = bool(TEST_RX.search(rel))
    if ext == ".py":
        for m in re.finditer(r"\brequests\.(get|post|put|patch|delete|head|request)\s*\(", text):
            flags["calls"] += 1
            if "timeout" not in call_text(text, m.start()) and not is_test:
                add("WARN", lineno(m.start()), f"requests.{m.group(1)}() without timeout", "no default timeout: one stalled server hangs the worker forever")
        for m in re.finditer(r"\burlopen\s*\(", text):
            flags["calls"] += 1
            if "timeout" not in call_text(text, m.start()) and not is_test:
                add("WARN", lineno(m.start()), "urlopen() without timeout", "blocks indefinitely on a stalled connection")
        for m in re.finditer(r"\b(httpx|aiohttp)\b", text):
            flags["calls"] += 1
            break
        for m in re.finditer(r"verify\s*=\s*False", text):
            add("WARN", lineno(m.start()), "TLS verification disabled (verify=False)", "exposes the connection to interception; fix the certificate instead")
    if ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        for m in re.finditer(r"\baxios\.(get|post|put|patch|delete|head|request)\s*\(|\baxios\s*\(", text):
            flags["calls"] += 1
            if "timeout" not in call_text(text, m.start()) and "timeout" not in text[:3000] and not is_test:
                add("INFO", lineno(m.start()), "axios call with no timeout in sight", "axios has no default timeout; set one per call or on the instance")
        for m in re.finditer(r"(?<![\w.])fetch\s*\(", text):
            flags["calls"] += 1
            c = call_text(text, m.start())
            if "signal" not in c and "AbortSignal" not in text and not is_test:
                add("INFO", lineno(m.start()), "fetch() without an abort signal/timeout", "fetch waits indefinitely; use AbortSignal.timeout(ms)")
        for m in re.finditer(r"rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['\"]?0", text):
            add("WARN", lineno(m.start()), "TLS verification disabled", "exposes the connection to interception")
    if ext == ".go":
        for m in re.finditer(r"\bhttp\.(Get|Post|PostForm|Head)\s*\(", text):
            flags["calls"] += 1
            add("WARN", lineno(m.start()), f"http.{m.group(1)}() uses the default client", "the default client has no timeout; use an http.Client{Timeout: ...}")
        for m in re.finditer(r"&?http\.Client\s*\{\s*\}", text):
            add("WARN", lineno(m.start()), "http.Client{} without Timeout", "requests can hang forever")
        for m in re.finditer(r"InsecureSkipVerify\s*:\s*true", text):
            add("WARN", lineno(m.start()), "InsecureSkipVerify: true", "TLS verification disabled")
    if ext in {".java", ".kt", ".cs", ".rb", ".php"}:
        for m in re.finditer(r"(?i)trustAll|ALLOW_ALL_HOSTNAME|VERIFY_NONE|CURLOPT_SSL_VERIFYPEER\s*,\s*(false|0)", text):
            add("WARN", lineno(m.start()), "TLS verification disabled", "exposes the connection to interception")

    if not is_test:
        for m in re.finditer(r"""['"](http://(?!localhost|127\.|0\.0\.0\.0|\[::1\]|host\.docker|example\.|.*\.local\b|.*\.test\b)[A-Za-z0-9.-]+\.[a-z]{2,}[^'"\s]*)['"]""", text):
            if "w3.org" in m.group(1) or "xmlns" in text[max(0, m.start() - 20) : m.start()]:
                continue
            add("INFO", lineno(m.start()), f"plain http URL: {m.group(1)[:60]}", "traffic is unencrypted; use https unless it is a local or internal test host")

    # webhooks
    if re.search(r"(?i)webhook", rel + " " + text[:20000]) and re.search(r"(?i)(route|post|app\.(post|use)|@(post|app)|handler|endpoint|def \w*webhook|function \w*webhook)", text[:20000]):
        if not re.search(r"(?i)signature|hmac|construct_event|verify_|verifysignature|svix|x-hub|timingSafeEqual|compare_digest", text):
            if not is_test:
                add("WARN", 1, "webhook handler with no signature verification in this file", "anyone can post fake events to a public URL; verify the provider's signature (HMAC) and reject replays")

    # retries
    if re.search(r"(?i)retry|backoff|tenacity|p-retry|axios-retry|got\(.*retry|urllib3\.util\.retry|resilience4j|polly", text):
        flags["retries"] = True

    # secrets
    if not rel.endswith((".example", ".sample")) and ".env.example" not in rel:
        flagged_lines = set()
        for label, rx in SECRET_FORMATS:
            for m in rx.finditer(text):
                flagged_lines.add(lineno(m.start()))
                if is_test and label in ("JWT",):
                    continue
                add("WARN", lineno(m.start()), f"possible {label}: {mask(m.group(0))}", "secrets in source end up in git history and logs; rotate it and load from the environment or a vault")
        for m in ASSIGN.finditer(text):
            val = m.group(2)
            if PLACEHOLDER.match(val) or is_test or re.fullmatch(r"[a-z_.]+", val) or lineno(m.start()) in flagged_lines:
                continue
            add("WARN", lineno(m.start()), f"hard-coded {m.group(1)} = {mask(val)}", "looks like a credential in source; load it from the environment or a secret store")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = Path(a.path).resolve()
    if not root.is_dir():
        print(f"error: {a.path} is not a directory", file=sys.stderr)
        return 1
    findings: list[dict] = []
    flags = {"calls": 0, "retries": False}
    n = 0
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.startswith(".") or d in (".github",)]
        for f in fn:
            p = Path(dp) / f
            ext = p.suffix.lower() if f != ".env" else ".env"
            if ext not in CODE_EXT or f.endswith((".min.js", "package-lock.json", ".lock")):
                continue
            try:
                if p.stat().st_size > 800_000:
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            n += 1
            rel = p.relative_to(root).as_posix()
            if f == ".env" or (f.startswith(".env.") and f not in (".env.example", ".env.sample", ".env.template")):
                findings.append({"severity": "WARN", "where": rel, "finding": "environment file present in the tree", "why": "make sure it is git-ignored and was never committed (git log --all -- " + rel + ")"})
                continue
            check_file(rel, text, ext, findings, flags)
    gi = root / ".gitignore"
    gtext = gi.read_text(encoding="utf-8", errors="replace") if gi.exists() else ""
    if (root / ".git").exists() and not re.search(r"^\s*\.env\b", gtext, re.M):
        findings.append({"severity": "WARN", "where": ".gitignore", "finding": ".env is not ignored", "why": "local secrets can be committed by accident"})
    if flags["calls"] and not (root / ".env.example").exists() and any(root.glob(".env*")):
        findings.append({"severity": "INFO", "where": ".", "finding": "no .env.example", "why": "document required settings with placeholder values"})
    if flags["calls"] and not flags["retries"]:
        findings.append({"severity": "INFO", "where": "(project)", "finding": f"{flags['calls']} outbound call site(s) and no retry/backoff logic found", "why": "transient failures (429, 503, timeouts) will surface as errors; add bounded retries with backoff for idempotent calls"})
    if a.json:
        print(json.dumps({"files": n, "outbound_call_sites": flags["calls"], "findings": findings}, indent=2))
        return 0
    print(f"Scanned {n} files; outbound call sites detected: {flags['calls']}\n")
    order = {"WARN": 0, "INFO": 1}
    for f in sorted(findings, key=lambda x: (order[x["severity"]], x["where"])):
        print(f"[{f['severity']}] {f['where']}: {f['finding']}\n        why: {f['why']}")
    w = sum(1 for f in findings if f["severity"] == "WARN")
    print(f"\n{w} warning(s), {len(findings) - w} note(s). Secret values are masked; if any are real, rotate them (removing them from the file does not remove them from git history).")
    print("Limits: textual; shared clients with a timeout set elsewhere, config-driven URLs and git history are not inspected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
