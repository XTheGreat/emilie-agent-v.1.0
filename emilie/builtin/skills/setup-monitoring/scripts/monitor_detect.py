#!/usr/bin/env python3
"""Detect observability tooling and gaps (read-only).

Usage: python monitor_detect.py [path]
"""
from __future__ import annotations
import re, sys
from pathlib import Path

SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "vendor", "target"}
EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java", ".kt", ".rb", ".php", ".rs", ".cs", ".yml", ".yaml", ".toml", ".json", ".txt", ".mod"}
TOOLS = {"prometheus": r"prometheus[_-]client|prom-client|/metrics\b|promhttp", "opentelemetry": r"opentelemetry|otel", "sentry": r"sentry[_-]sdk|@sentry/|sentry\.io",
         "datadog": r"ddtrace|dd-trace|datadog", "structlog/json logging": r"structlog|python-json-logger|pino|winston|zerolog|slog\.", "statsd": r"statsd", "newrelic": r"newrelic"}
HEALTH = re.compile(r"['\"/](healthz?|readyz?|livez?|health_check|ping)['\"/ ]", re.I)

def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    hits = {k: 0 for k in TOOLS}; health, prints, bare_except, loggers, n = [], 0, 0, 0, 0
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in EXT or (set(p.relative_to(root).parts) & SKIP) or p.stat().st_size > 400_000: continue
        t = p.read_text(errors="ignore"); n += 1; rel = str(p.relative_to(root))
        for k, rx in TOOLS.items():
            if re.search(rx, t, re.I): hits[k] += 1
        if HEALTH.search(t) and p.suffix in {".py", ".js", ".ts", ".go", ".java", ".kt", ".rb", ".php", ".rs", ".cs"}: health.append(rel)
        if p.suffix == ".py":
            prints += len(re.findall(r"^\s*print\(", t, re.M)); loggers += len(re.findall(r"\blogging\.|getLogger\(", t))
            bare_except += len(re.findall(r"except[^\n]*:\s*\n\s*(pass|continue)\b", t))
        if p.suffix in {".js", ".ts"}: prints += len(re.findall(r"console\.(log|error)\(", t))
    print(f"files scanned: {n}")
    print("observability tooling found:", {k: v for k, v in hits.items() if v} or "none")
    print("health endpoints mentioned in:", health[:6] or "none found -> add /healthz and /readyz")
    print(f"bare print/console logging: {prints}; logging module uses: {loggers}; swallowed exceptions (except: pass): {bare_except}")
    gaps = []
    if not hits["prometheus"] and not hits["opentelemetry"] and not hits["datadog"] and not hits["statsd"]: gaps.append("no metrics library")
    if not hits["sentry"] and not hits["opentelemetry"]: gaps.append("no error tracking or tracing")
    if not health: gaps.append("no health endpoint")
    if prints > 20 and not hits["structlog/json logging"]: gaps.append("unstructured print logging")
    if bare_except: gaps.append("exceptions swallowed silently")
    print("GAPS:", gaps or "none obvious")
    return 0

if __name__ == "__main__": sys.exit(main())
