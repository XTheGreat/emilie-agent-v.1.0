#!/usr/bin/env python3
"""Triage a log file (read-only, stdlib): levels, error clusters, first occurrence, rate over time, status codes, slow requests.

Usage: python log_triage.py <file|-> [--since "YYYY-MM-DD HH:MM"] [--top 10]
Handles plain text and JSON-lines logs. Values that look like tokens are masked in output.
"""
from __future__ import annotations
import argparse, json, re, sys
from collections import Counter, defaultdict

TS = re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})")
LEVEL = re.compile(r"\b(CRITICAL|FATAL|ERROR|WARN(?:ING)?|INFO|DEBUG)\b", re.I)
STATUS = re.compile(r'"\s*(\d{3})\s+\d+|\bstatus[=: ]+(\d{3})\b', re.I)
DUR = re.compile(r"\b(?:took|duration|elapsed|latency|time)[=: ]+(\d+(?:\.\d+)?)\s*(ms|s)\b", re.I)
MASK = re.compile(r"(?i)(bearer\s+|token=|password=|secret=|api[_-]?key=)[^\s&\"']+|\b[A-Za-z0-9_-]{32,}\b|[\w.+-]+@[\w-]+\.[\w.]+")

def norm(m):
    m = MASK.sub("<masked>", m)
    m = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27}\b", "<uuid>", m)
    m = re.sub(r"0x[0-9a-f]+|\b\d+(\.\d+)*\b", "<n>", m)
    return m[:140]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("file"); ap.add_argument("--since"); ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()
    f = sys.stdin if a.file == "-" else open(a.file, errors="ignore")
    lv, clusters, first, per_min, codes, slow = Counter(), Counter(), {}, defaultdict(Counter), Counter(), []
    total = 0
    for line in f:
        total += 1; text = line
        if line.lstrip().startswith("{"):
            try:
                d = json.loads(line); text = " ".join(str(v) for v in d.values()) if isinstance(d, dict) else line
                ts = str(d.get("timestamp") or d.get("time") or d.get("ts") or ""); lvl = str(d.get("level") or d.get("severity") or "")
                text = f"{ts} {lvl} {d.get('message') or d.get('msg') or text}"
            except ValueError: pass
        m = TS.search(text)
        stamp = f"{m.group(1)} {m.group(2)}:{m.group(3)}" if m else None
        if a.since and stamp and stamp < a.since: continue
        l = LEVEL.search(text); level = l.group(1).upper().replace("WARNING", "WARN") if l else "?"
        lv[level] += 1
        if level in ("ERROR", "CRITICAL", "FATAL"):
            key = norm(LEVEL.sub("", TS.sub("", text)).strip(" -:[]"))
            clusters[key] += 1
            if key not in first: first[key] = (stamp or "?", total)
            if stamp: per_min[stamp][level] += 1
        s = STATUS.search(text)
        if s: codes[s.group(1) or s.group(2)] += 1
        d = DUR.search(text)
        if d:
            ms = float(d.group(1)) * (1000 if d.group(2).lower() == "s" else 1)
            slow.append((ms, norm(text)[:100]))
    print(f"lines: {total}\nlevels: {dict(lv)}")
    print(f"\nTOP ERROR CLUSTERS (count, first seen, line):")
    for k, n in clusters.most_common(a.top): print(f"  {n:6}  {first[k][0]}  L{first[k][1]}  {k}")
    if per_min:
        rows = sorted(per_min.items()); peak = max(rows, key=lambda r: sum(r[1].values()))
        print(f"\nerror rate: first minute with errors {rows[0][0]}, peak {peak[0]} ({sum(peak[1].values())}/min), last {rows[-1][0]}")
    if codes: print("\nstatus codes:", dict(codes.most_common(8)))
    if slow:
        slow.sort(reverse=True); vals = sorted(x[0] for x in slow); p95 = vals[int(len(vals) * 0.95) - 1] if len(vals) > 20 else vals[-1]
        print(f"\ntimings: n={len(vals)} p50={vals[len(vals)//2]:.0f}ms p95={p95:.0f}ms max={vals[-1]:.0f}ms"); [print(f"  {ms:8.0f}ms {t}") for ms, t in slow[:5]]
    print("\nnext: correlate the first-seen time with deploys/config changes; follow one failing request id end to end.")
    return 0

if __name__ == "__main__": sys.exit(main())
