#!/usr/bin/env python3
"""A small, honest HTTP load generator (standard library only).

Usage:
  python loadtest.py URL [-c 10] [-d 10] [--rps N] [--ramp S] [--warmup S] [-X METHOD] [-H "Name: value" ...]
                          [--data TEXT|@file] [--timeout 10] [--max-p95-ms MS] [--max-error-rate PCT] [--json]
                          [--allow-remote] [--insecure]

Closed loop (default): -c workers each send a request, wait for the answer, repeat - the classic "N concurrent users" test.
Open loop (--rps N): requests are SCHEDULED at N per second in total, and latency is measured from the intended start time, so a
slow server cannot hide its queueing (avoids "coordinated omission"). Use it to answer "can it sustain N requests per second?".

Reports requests, throughput, status codes, errors, latency percentiles (p50/p90/p95/p99/max), a per-second timeline, and checks
optional thresholds (exit code 1 when exceeded). --warmup seconds are sent but not counted.

SAFETY: loading a system you do not own is an attack. By default only localhost, loopback and private-network addresses are allowed;
anything else needs --allow-remote, which you may use only on systems you own or have written permission to test. Limits: at most
500 workers and 600 s unless --force-large. The generator is a Python threaded client: on one machine it tops out at a few thousand
requests per second, and its own CPU can become the bottleneck - watch for that before blaming the server.
"""
from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import socket
import ssl
import sys
import threading
import time
from collections import Counter
from urllib.parse import urlsplit


def is_local(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not (ip.is_loopback or ip.is_private or ip.is_link_local):
            return False
    return True


def pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p / 100
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


class Worker(threading.Thread):
    def __init__(self, idx, cfg, results, stop_at, start_at, interval):
        super().__init__(daemon=True)
        self.idx, self.cfg, self.results, self.stop_at, self.start_at, self.interval = idx, cfg, results, stop_at, start_at, interval
        self.conn = None

    def connect(self):
        c = self.cfg
        if c["scheme"] == "https":
            ctx = ssl._create_unverified_context() if c["insecure"] else ssl.create_default_context()
            self.conn = http.client.HTTPSConnection(c["host"], c["port"], timeout=c["timeout"], context=ctx)
        else:
            self.conn = http.client.HTTPConnection(c["host"], c["port"], timeout=c["timeout"])

    def run(self):
        c = self.cfg
        delay = self.start_at - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        next_due = time.perf_counter()
        while True:
            now = time.perf_counter()
            if now >= self.stop_at:
                return
            if self.interval:                              # open loop: wait for the scheduled slot
                if next_due > now:
                    time.sleep(min(next_due - now, self.stop_at - now))
                    if time.perf_counter() >= self.stop_at:
                        return
                intended = next_due
                next_due += self.interval
            else:
                intended = time.perf_counter()
            status, err = None, None
            try:
                if self.conn is None:
                    self.connect()
                self.conn.request(c["method"], c["path"], body=c["body"], headers=c["headers"])
                resp = self.conn.getresponse()
                resp.read()
                status = resp.status
                if resp.getheader("Connection", "").lower() == "close":
                    self.conn.close()
                    self.conn = None
            except socket.timeout:
                err = "timeout"
            except (ConnectionError, http.client.HTTPException, ssl.SSLError, OSError) as e:
                err = type(e).__name__
            if err and self.conn is not None:
                try:
                    self.conn.close()
                except OSError:
                    pass
                self.conn = None
            done = time.perf_counter()
            self.results.append((done, done - intended, status, err))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("-c", "--concurrency", type=int, default=10)
    ap.add_argument("-d", "--duration", type=float, default=10)
    ap.add_argument("--rps", type=float, default=0)
    ap.add_argument("--ramp", type=float, default=0)
    ap.add_argument("--warmup", type=float, default=0)
    ap.add_argument("-X", "--method", default="GET")
    ap.add_argument("-H", "--header", action="append", default=[])
    ap.add_argument("--data")
    ap.add_argument("--timeout", type=float, default=10)
    ap.add_argument("--max-p95-ms", type=float)
    ap.add_argument("--max-error-rate", type=float, help="percent of failed requests allowed (errors and HTTP >= 500; 4xx counted if --count-4xx)")
    ap.add_argument("--count-4xx", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--allow-remote", action="store_true")
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--force-large", action="store_true")
    a = ap.parse_args()

    u = urlsplit(a.url if "://" in a.url else "http://" + a.url)
    if u.scheme not in ("http", "https") or not u.hostname:
        print("error: URL must be http:// or https://", file=sys.stderr)
        return 2
    if not is_local(u.hostname) and not a.allow_remote:
        print(f"refused: {u.hostname} is not a local/private address. Load testing a system you do not own is an attack.\n"
              f"If you own it or have written permission, run again with --allow-remote.", file=sys.stderr)
        return 2
    if (a.concurrency > 500 or a.duration > 600) and not a.force_large:
        print("refused: more than 500 workers or 600 s. Use --force-large if you really mean it.", file=sys.stderr)
        return 2
    if a.concurrency < 1 or a.duration <= 0:
        print("error: concurrency must be >= 1 and duration > 0", file=sys.stderr)
        return 2
    headers = {}
    for h in a.header:
        k, _, v = h.partition(":")
        headers[k.strip()] = v.strip()
    body = None
    if a.data is not None:
        body = open(a.data[1:], "rb").read() if a.data.startswith("@") else a.data.encode()
        headers.setdefault("Content-Type", "application/json" if (body[:1] in (b"{", b"[")) else "application/x-www-form-urlencoded")
    headers.setdefault("User-Agent", "emilie-loadtest/1")
    port = u.port or (443 if u.scheme == "https" else 80)
    path = (u.path or "/") + (("?" + u.query) if u.query else "")
    cfg = {"scheme": u.scheme, "host": u.hostname, "port": port, "path": path, "method": a.method.upper(), "headers": headers,
           "body": body, "timeout": a.timeout, "insecure": a.insecure}

    results: list = []
    t0 = time.perf_counter()
    total = a.duration + a.warmup
    stop_at = t0 + total
    interval = (a.concurrency / a.rps) if a.rps else 0.0
    workers = []
    for i in range(a.concurrency):
        start = t0 + (a.ramp * i / a.concurrency if a.ramp else 0.0) + (i * interval / a.concurrency if interval else 0.0)
        workers.append(Worker(i, cfg, results, stop_at, start, interval))
    if not a.json:
        mode = f"open loop {a.rps:g} req/s" if a.rps else f"closed loop, {a.concurrency} concurrent"
        print(f"{cfg['method']} {a.url}  |  {mode}  |  {a.duration:g}s" + (f" (+{a.warmup:g}s warm-up)" if a.warmup else "") + (f", ramp {a.ramp:g}s" if a.ramp else ""))
    for w in workers:
        w.start()
    try:
        while time.perf_counter() < stop_at + a.timeout + 1 and any(w.is_alive() for w in workers):
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\ninterrupted: reporting what was collected", file=sys.stderr)
    measured = [r for r in list(results) if r[0] >= t0 + a.warmup]
    span = max(a.duration, 1e-9)
    if not measured:
        print("No requests completed. Is the server reachable?", file=sys.stderr)
        return 2
    lats = sorted(r[1] * 1000 for r in measured)
    codes = Counter(r[2] for r in measured if r[2] is not None)
    errs = Counter(r[3] for r in measured if r[3])
    n = len(measured)
    bad = sum(1 for r in measured if r[3] or (r[2] is not None and (r[2] >= 500 or (a.count_4xx and r[2] >= 400))))
    err_rate = 100.0 * bad / n
    seconds: dict[int, list] = {}
    for done, lat, st, er in measured:
        seconds.setdefault(min(int(done - t0 - a.warmup), max(int(a.duration) - 1, 0)), []).append((lat * 1000, bool(er or (st and st >= 500))))
    out = {
        "requests": n, "seconds": round(span, 1), "rps": round(n / span, 1), "errors": bad, "error_rate_pct": round(err_rate, 2),
        "status": {str(k): v for k, v in sorted(codes.items())}, "error_types": dict(errs),
        "latency_ms": {"min": round(lats[0], 1), "mean": round(sum(lats) / n, 1), "p50": round(pct(lats, 50), 1), "p90": round(pct(lats, 90), 1),
                       "p95": round(pct(lats, 95), 1), "p99": round(pct(lats, 99), 1), "max": round(lats[-1], 1)},
        "timeline": [{"second": s, "rps": len(v), "p95_ms": round(pct(sorted(x[0] for x in v), 95), 1), "errors": sum(1 for x in v if x[1])}
                     for s, v in sorted(seconds.items())],
    }
    failed = []
    if a.max_p95_ms is not None and out["latency_ms"]["p95"] > a.max_p95_ms:
        failed.append(f"p95 {out['latency_ms']['p95']} ms > {a.max_p95_ms} ms")
    if a.max_error_rate is not None and err_rate > a.max_error_rate:
        failed.append(f"error rate {err_rate:.2f}% > {a.max_error_rate}%")
    out["thresholds_failed"] = failed
    if a.json:
        print(json.dumps(out, indent=2))
        return 1 if failed else 0
    L = out["latency_ms"]
    print(f"\nrequests: {n}   throughput: {out['rps']} req/s   errors: {bad} ({err_rate:.2f}%)")
    print("status codes: " + (", ".join(f"{k}: {v}" for k, v in out["status"].items()) or "none") + ("   transport errors: " + ", ".join(f"{k}: {v}" for k, v in errs.items()) if errs else ""))
    print(f"latency ms: min {L['min']}  mean {L['mean']}  p50 {L['p50']}  p90 {L['p90']}  p95 {L['p95']}  p99 {L['p99']}  max {L['max']}")
    print("\nper second:   req/s   p95 ms   errors")
    shown = out["timeline"]
    if len(shown) > 20:
        step = max(1, len(shown) // 20)
        shown = shown[::step]
    for row in shown:
        print(f"  t+{row['second']:>4}s    {row['rps']:>5}  {row['p95_ms']:>7}   {row['errors']:>5}")
    buckets = [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
    print("\nlatency histogram:")
    prev = 0
    for b in buckets + [float("inf")]:
        cnt = sum(1 for x in lats if prev <= x < b)
        if cnt:
            label = f"{prev:g}-{b:g} ms" if b != float("inf") else f">= {prev:g} ms"
            print(f"  {label:>14} {cnt:>7} {'#' * max(1, round(40 * cnt / n))}")
        prev = b
    if a.rps and out["rps"] < a.rps * 0.95:
        print(f"\nNOTE: the achieved rate ({out['rps']}/s) is below the target ({a.rps:g}/s): the server (or this generator) could not keep up.")
    print("\nBefore trusting the numbers: was the client machine saturated (CPU)? Is the target the real stack (same config, data size, TLS)? Did the run include warm-up?")
    if failed:
        print("\nTHRESHOLDS EXCEEDED: " + "; ".join(failed))
        return 1
    if bad == n:
        print("\nEvery request failed: nothing was measured about performance (check the URL, the server and the network).")
        return 1
    if a.max_p95_ms is not None or a.max_error_rate is not None:
        print("\nThresholds met.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
