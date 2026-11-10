#!/usr/bin/env python3
"""List and lint HTTP API endpoints from an OpenAPI file or from source code.

Usage:
  python api_lint.py <openapi.json | openapi.yaml | source-dir> [--json]

* OpenAPI (JSON always; YAML only if PyYAML is installed) -> full contract checks.
* A directory -> endpoints are discovered with regexes for Flask, FastAPI,
  Express/Koa-style routers, Django `path()`, Spring mappings, and Go/Gin-style
  routers, then the paths are checked for consistency.

Read-only, standard library only. Findings are questions to answer, not verdicts.
Limits: source discovery is textual; routes built dynamically, mounted under a
prefix elsewhere (`app.use('/api', router)`, `include_router(prefix=...)`) or
declared in config are missing or shown without their prefix.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "out", "vendor", "target", ".next", "site-packages"}
METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
VERBS = re.compile(r"^(get|fetch|list|create|add|new|update|edit|set|delete|remove|do|make|find|search|run|execute)([A-Z_\-]|$)", re.I)
PARAM = re.compile(r"\{[^}]+\}|:[A-Za-z_]\w*|<[^>]+>")

FRAMEWORKS = [
    # (name, regex, method group index or fixed, path group index)
    ("flask-route", re.compile(r"@\w+\.route\(\s*['\"]([^'\"]+)['\"](?:[^)]*?methods\s*=\s*\[([^\]]*)\])?"), None, 1),
    ("py-decorator", re.compile(r"@\w+\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]*)['\"]", re.I), 1, 2),
    ("express", re.compile(r"\b(?:app|router|api|server|routes?|\w+Router|\w+App)\.(get|post|put|patch|delete)\(\s*['\"`](/[^'\"`]*)['\"`]"), 1, 2),
    ("spring-mapping", re.compile(r"@(Get|Post|Put|Patch|Delete)Mapping\(\s*(?:value\s*=\s*)?\{?\s*['\"]([^'\"]*)['\"]"), 1, 2),
    ("go-router", re.compile(r"\b\w+\.(GET|POST|PUT|PATCH|DELETE)\(\s*\"([^\"]*)\""), 1, 2),
    ("go-handle", re.compile(r"\.(?:HandleFunc|Handle)\(\s*\"([^\"]*)\""), None, 1),
    ("django-path", re.compile(r"\b(?:re_)?path\(\s*r?['\"]([^'\"]*)['\"]\s*,"), None, 1),
]
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|e2e|cypress|fixtures?)(/|$)|\.(test|spec)\.|_test\.", re.I)


def norm(path: str) -> str:
    p = PARAM.sub("{}", path)
    return p if p == "/" else p.rstrip("/")


def discover(root: Path):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if Path(fn).suffix not in {".py", ".js", ".ts", ".mjs", ".cjs", ".java", ".kt", ".go"}:
                continue
            p = Path(dirpath) / fn
            rel = p.relative_to(root).as_posix()
            if TEST_PATH.search(rel):
                continue
            try:
                if p.stat().st_size > 1_500_000:
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for name, rx, mgrp, pgrp in FRAMEWORKS:
                for m in rx.finditer(text):
                    path = m.group(pgrp)
                    if name in ("django-path", "go-handle") and not path.startswith("/"):
                        path = "/" + path
                    if name == "flask-route":
                        ms = re.findall(r"['\"](\w+)['\"]", m.group(2) or "") or ["GET"]
                    elif mgrp:
                        ms = [m.group(mgrp)]
                    else:
                        ms = ["ANY"]
                    line = text.count("\n", 0, m.start()) + 1
                    for meth in ms:
                        found.append({"method": meth.upper(), "path": path or "/", "where": f"{rel}:{line}", "kind": name})
    # de-duplicate identical regex hits (e.g. flask-route vs py-decorator overlap)
    seen, out = set(), []
    for e in found:
        k = (e["method"], e["path"], e["where"])
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out


def seg_style(seg: str) -> str | None:
    if PARAM.fullmatch(seg) or not re.search(r"[A-Za-z]", seg):
        return None
    if re.search(r"[a-z][A-Z]", seg):
        return "camelCase"
    if "_" in seg:
        return "snake_case"
    if "-" in seg:
        return "kebab-case"
    return "single-word"


def lint_paths(eps: list[dict]) -> list[dict]:
    out = []

    def add(sev, ep, msg, why):
        out.append({"severity": sev, "endpoint": ep, "finding": msg, "why": why})

    paths = sorted({e["path"] for e in eps})
    styles = {}
    for p in paths:
        for seg in p.strip("/").split("/"):
            s = seg_style(seg)
            if s and s != "single-word":
                styles.setdefault(s, []).append(p)
    if len(styles) > 1:
        add("WARN", "(all)", "mixed path casing: " + ", ".join(f"{k} ({len(v)})" for k, v in styles.items()), "pick one style (kebab-case or snake_case) for all path segments")
    with_slash = [p for p in paths if len(p) > 1 and p.endswith("/")]
    if with_slash and len(with_slash) != len([p for p in paths if len(p) > 1]):
        add("INFO", "(all)", "trailing slash used on some paths only", "choose one form and redirect or reject the other")
    if paths and not any(re.match(r"^/(api/)?v\d+(/|$)", p) for p in paths):
        add("INFO", "(all)", "no version in any path", "decide the versioning strategy (path, header, or none for internal APIs) and record it")
    seen = {}
    for e in eps:
        key = (e["method"], norm(e["path"]))
        if key in seen and e["method"] != "ANY":
            add("WARN", f"{e['method']} {e['path']}", f"defined more than once ({seen[key]} and {e['where']})", "the later definition may shadow the earlier one")
        seen.setdefault(key, e["where"])
        segs = [s for s in e["path"].strip("/").split("/") if s]
        static = [s for s in segs if not PARAM.fullmatch(s)]
        for s in static:
            if VERBS.match(s) and not re.fullmatch(r"v\d+|api", s):
                if e["method"] == "GET" and re.match(r"^(delete|remove|create|add|update|edit|set)", s, re.I):
                    add("WARN", f"{e['method']} {e['path']}", f"GET with action word '{s}'", "GET must be safe; a state change on GET is triggered by crawlers, prefetch and link previews")
                else:
                    add("INFO", f"{e['method']} {e['path']}", f"verb '{s}' in the path", "model a resource and use the HTTP method as the verb; use an action sub-resource only for real commands")
                break
        if len(static) > 3:
            add("INFO", f"{e['method']} {e['path']}", f"{len(static)} nested segments", "deep nesting couples URLs to hierarchies; prefer shallow resources with filters")
        if re.search(r"\.(json|xml|php|aspx?)$", e["path"]):
            add("INFO", f"{e['method']} {e['path']}", "file extension in path", "use content negotiation (Accept header) instead")
        if re.search(r"[A-Z]", "".join(static)) and not re.search(r"[a-z][A-Z]", "".join(static)):
            add("INFO", f"{e['method']} {e['path']}", "uppercase in path", "URLs are case sensitive in the path; keep them lowercase")
    return out


def lint_openapi(doc: dict) -> tuple[list[dict], list[dict]]:
    eps, out = [], []

    def add(sev, ep, msg, why):
        out.append({"severity": sev, "endpoint": ep, "finding": msg, "why": why})

    paths = doc.get("paths") or {}
    has_global_security = bool(doc.get("security"))
    schemes = (doc.get("components") or {}).get("securitySchemes") or doc.get("securityDefinitions")
    if not doc.get("servers") and "swagger" not in doc:
        add("INFO", "(spec)", "no servers listed", "clients cannot discover the base URL")
    if not (doc.get("info") or {}).get("version"):
        add("INFO", "(spec)", "info.version missing", "version the contract so changes are traceable")
    if not schemes:
        add("WARN", "(spec)", "no security schemes defined", "state how callers authenticate, or that the API is intentionally public")
    ids = {}
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        shared_params = item.get("parameters", [])
        declared_in_path = set(re.findall(r"\{([^}]+)\}", path))
        for meth, op in item.items():
            if meth.lower() not in METHODS or not isinstance(op, dict):
                continue
            m = meth.upper()
            ep = f"{m} {path}"
            eps.append({"method": m, "path": path, "where": "openapi", "kind": "openapi"})
            params = list(shared_params) + list(op.get("parameters", []))
            pnames = {p.get("name") for p in params if isinstance(p, dict)}
            for need in declared_in_path - pnames:
                add("WARN", ep, f"path parameter '{need}' not declared", "tools and validators cannot check or document it")
            for p in params:
                if isinstance(p, dict) and "$ref" not in p and not p.get("schema") and not p.get("type") and not p.get("content"):
                    add("INFO", ep, f"parameter '{p.get('name')}' has no schema", "give every parameter a type")
            resp = op.get("responses") or {}
            codes = {str(c) for c in resp}
            if not resp:
                add("WARN", ep, "no responses documented", "clients cannot know what to expect")
            else:
                if not any(c.startswith(("4", "5")) or c == "default" for c in codes):
                    add("WARN", ep, "no error responses documented", "document at least the 400/401/403/404/409/422 cases that can happen and the error body shape")
                if m == "POST" and "201" not in codes and "202" not in codes and any(c in codes for c in ("200",)) and "{" not in path.rsplit("/", 1)[-1]:
                    add("INFO", ep, "POST creating a resource returns 200 only", "use 201 with a Location header (or 202 for async work) if this creates something")
                if m == "DELETE" and not codes & {"200", "202", "204"}:
                    add("INFO", ep, "DELETE has no success response", "usually 204")
            if m in ("GET", "DELETE") and op.get("requestBody"):
                add("WARN", ep, f"{m} has a request body", "many clients, caches and proxies drop or reject bodies on this method")
            if not op.get("operationId"):
                add("INFO", ep, "no operationId", "generated clients and docs need stable operation names")
            else:
                if op["operationId"] in ids:
                    add("WARN", ep, f"operationId '{op['operationId']}' duplicates {ids[op['operationId']]}", "ids must be unique")
                ids[op["operationId"]] = ep
            if not (op.get("summary") or op.get("description")):
                add("INFO", ep, "no summary or description", "document what it does, who can call it and what it changes")
            if m == "GET" and not declared_in_path:
                ok = resp.get("200") or resp.get("default") or {}
                content = (ok.get("content") or {}).get("application/json", {}) if isinstance(ok, dict) else {}
                sch = content.get("schema", {}) if isinstance(content, dict) else {}
                is_list = sch.get("type") == "array" or (isinstance(sch.get("properties"), dict) and any(
                    isinstance(v, dict) and v.get("type") == "array" for v in sch["properties"].values()))
                if is_list and not any(re.fullmatch(r"(limit|page|per_?page|page_?size|cursor|offset|after|before|size|take|skip)", str(n), re.I) for n in pnames):
                    add("WARN", ep, "list endpoint without pagination parameters", "unbounded lists break as data grows; add limit plus cursor or page")
            if m != "GET" and not has_global_security and not op.get("security") and schemes:
                add("WARN", ep, "write operation with no security requirement", "confirm it is meant to be public")
    return eps, out


def load_doc(p: Path):
    text = p.read_text(encoding="utf-8", errors="replace")
    if p.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml  # type: ignore
    except ImportError:
        raise SystemExit("This is YAML and PyYAML is not installed. Convert to JSON or `pip install pyyaml`, or read the file by hand.")
    return yaml.safe_load(text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    t = Path(a.target)
    if not t.exists():
        print(f"error: {a.target} not found", file=sys.stderr)
        return 1
    mode = "source"
    findings: list[dict] = []
    if t.is_file():
        try:
            doc = load_doc(t)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"error: cannot parse {t}: {e}", file=sys.stderr)
            return 1
        if not isinstance(doc, dict) or not ("openapi" in doc or "swagger" in doc):
            print("error: file is not an OpenAPI/Swagger document", file=sys.stderr)
            return 1
        mode = f"openapi {doc.get('openapi') or doc.get('swagger')}"
        eps, findings = lint_openapi(doc)
        findings += lint_paths(eps)
    else:
        eps = discover(t)
        findings = lint_paths(eps)
    if a.json:
        print(json.dumps({"mode": mode, "endpoints": eps, "findings": findings}, indent=2))
        return 0
    print(f"Mode: {mode} | endpoints: {len(eps)}\n")
    for e in sorted(eps, key=lambda x: (norm(x["path"]), x["method"])):
        print(f"  {e['method']:7} {e['path']:45} {e['where']}")
    if not eps:
        print("  none found (routes may be mounted dynamically or defined by a framework not covered)")
    print()
    order = {"WARN": 0, "INFO": 1}
    for f in sorted(findings, key=lambda x: (order[x["severity"]], x["endpoint"])):
        print(f"[{f['severity']}] {f['endpoint']}: {f['finding']}\n        why: {f['why']}")
    w = sum(1 for f in findings if f["severity"] == "WARN")
    print(f"\n{w} warning(s), {len(findings) - w} note(s). Findings are prompts to decide, not verdicts.")
    if mode == "source":
        print("Limits: textual route discovery; prefixes added by mounting (app.use, include_router, context-path) are not applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
