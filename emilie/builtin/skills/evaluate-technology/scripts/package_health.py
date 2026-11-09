#!/usr/bin/env python3
"""Health facts about libraries, from the public package registries (and GitHub when a repository is listed).

    python package_health.py <ecosystem> <name> [<name> ...]
    ecosystems: pypi | npm | crates | go          (go names are module paths, e.g. github.com/gin-gonic/gin)

It only READS public, unauthenticated APIs (PyPI, npm, crates.io, the Go module proxy, api.github.com). It prints
facts and plain warnings, never a verdict: popularity and recent releases are signals, not proof of fit. GitHub allows
60 unauthenticated requests per hour; set GITHUB_TOKEN to raise that (the token is only sent to api.github.com and is
never printed). Needs network access; on failure it says so and exits 1.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "emilie-package-health/1.0 (+read-only)"
NOW = dt.datetime.now(dt.timezone.utc)


def get(url: str, host_token: bool = False) -> dict | list | None:
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if host_token and os.environ.get("GITHUB_TOKEN") and urllib.parse.urlparse(url).hostname == "api.github.com":
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        if e.code in (403, 429):
            raise RuntimeError(f"rate limited by {urllib.parse.urlparse(url).hostname} (HTTP {e.code})") from None
        raise RuntimeError(f"HTTP {e.code} from {urllib.parse.urlparse(url).hostname}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"cannot reach {urllib.parse.urlparse(url).hostname}: {getattr(e, 'reason', e)}") from None


def when(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def age(d: dt.datetime | None) -> str:
    if not d:
        return "unknown"
    days = (NOW - d).days
    if days < 60:
        return f"{days} days ago"
    if days < 700:
        return f"{days // 30} months ago"
    return f"{days / 365:.1f} years ago"


def github_slug(*urls: str | None) -> str | None:
    for u in urls:
        m = re.search(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git|/|#|$)", u or "")
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    return None


def github(slug: str | None) -> dict:
    if not slug:
        return {}
    try:
        d = get(f"https://api.github.com/repos/{slug}", host_token=True)
    except RuntimeError as e:
        return {"github_error": str(e)}
    if not d:
        return {"github_error": "repository not found (renamed, moved or private)"}
    return {"repo": slug, "stars": d.get("stargazers_count"), "forks": d.get("forks_count"),
            "open_issues": d.get("open_issues_count"), "pushed": when(d.get("pushed_at")), "archived": d.get("archived"),
            "gh_license": (d.get("license") or {}).get("spdx_id"), "created": when(d.get("created_at"))}


def cadence(times: list[dt.datetime]) -> str:
    year = [t for t in times if t and (NOW - t).days <= 365]
    return f"{len(year)} releases in the last 12 months ({len(times)} total)"


def pypi(name: str) -> dict | None:
    d = get(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json")
    if not d:
        return None
    info, rel = d["info"], d.get("releases", {})
    times = [when((files[0] if files else {}).get("upload_time_iso_8601")) for files in rel.values() if files]
    times = [t for t in times if t]
    urls = info.get("project_urls") or {}
    repo = github_slug(*urls.values(), info.get("home_page"))
    classifiers = [c for c in info.get("classifiers", []) if c.startswith("Development Status")]
    lic = info.get("license_expression") or (info.get("license") or "")[:40] or next(
        (c.split("::")[-1].strip() for c in info.get("classifiers", []) if c.startswith("License ::")), "")
    return {"name": info["name"], "version": info["version"], "license": lic, "requires": info.get("requires_python"),
            "released": max(times) if times else None, "first": min(times) if times else None, "cadence": cadence(times),
            "deps": len(info.get("requires_dist") or []), "status": classifiers[0].split("::")[-1].strip() if classifiers else "",
            "deprecated": "yanked" if info.get("yanked") else "", "summary": (info.get("summary") or "")[:100],
            "gh": github(repo), "repo_known": bool(repo)}


def npm(name: str) -> dict | None:
    d = get(f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='@')}")
    if not d:
        return None
    latest = d.get("dist-tags", {}).get("latest")
    v = d.get("versions", {}).get(latest, {})
    t = d.get("time", {})
    times = [when(x) for k, x in t.items() if k not in ("created", "modified")]
    times = [x for x in times if x]
    dl = None
    try:
        dl = (get(f"https://api.npmjs.org/downloads/point/last-month/{urllib.parse.quote(name, safe='@')}") or {}).get("downloads")
    except RuntimeError:
        pass
    repo = github_slug((d.get("repository") or {}).get("url") if isinstance(d.get("repository"), dict) else d.get("repository"),
                       d.get("homepage"))
    return {"name": d.get("name", name), "version": latest, "license": v.get("license") or d.get("license") or "",
            "requires": (v.get("engines") or {}).get("node"), "released": when(t.get(latest)), "first": when(t.get("created")),
            "cadence": cadence(times), "deps": len(v.get("dependencies") or {}), "status": "",
            "deprecated": (v.get("deprecated") or "")[:120], "summary": (d.get("description") or "")[:100],
            "maintainers": len(d.get("maintainers") or []), "downloads_month": dl, "gh": github(repo), "repo_known": bool(repo)}


def crates(name: str) -> dict | None:
    d = get(f"https://crates.io/api/v1/crates/{urllib.parse.quote(name)}")
    if not d:
        return None
    c, vs = d["crate"], d.get("versions", [])
    times = [when(v.get("created_at")) for v in vs if not v.get("yanked")]
    times = [x for x in times if x]
    newest = vs[0] if vs else {}
    repo = github_slug(c.get("repository"), c.get("homepage"))
    return {"name": c["name"], "version": c.get("max_stable_version") or c.get("newest_version"), "license": newest.get("license") or "",
            "requires": newest.get("rust_version"), "released": when(newest.get("created_at")), "first": when(c.get("created_at")),
            "cadence": cadence(times), "deps": None, "status": "", "deprecated": "yanked" if newest.get("yanked") else "",
            "summary": (c.get("description") or "")[:100], "downloads_total": c.get("downloads"),
            "downloads_recent": c.get("recent_downloads"), "gh": github(repo), "repo_known": bool(repo)}


def gomod(name: str) -> dict | None:
    esc = re.sub(r"[A-Z]", lambda m: "!" + m.group(0).lower(), name)
    d = get(f"https://proxy.golang.org/{esc}/@latest")
    if not d:
        return None
    return {"name": name, "version": d.get("Version"), "license": "(see repository)", "requires": None,
            "released": when(d.get("Time")), "first": None, "cadence": "not available from the module proxy", "deps": None,
            "status": "", "deprecated": "", "summary": "", "gh": github(github_slug(f"https://{name}")),
            "repo_known": name.startswith("github.com/")}


FETCH = {"pypi": pypi, "npm": npm, "crates": crates, "go": gomod}


def warnings(r: dict) -> list[str]:
    w = []
    if r.get("deprecated"):
        w.append(f"DEPRECATED/YANKED: {r['deprecated']}")
    gh = r.get("gh") or {}
    if gh.get("archived"):
        w.append("repository is ARCHIVED (read-only, no more fixes)")
    rel = r.get("released")
    if rel and (NOW - rel).days > 548:
        w.append(f"last release {age(rel)}: may be unmaintained")
    pushed = gh.get("pushed")
    if pushed and (NOW - pushed).days > 548:
        w.append(f"last commit {age(pushed)}")
    if not r.get("license"):
        w.append("no license declared: check before using")
    first = r.get("first")
    if first and (NOW - first).days < 180:
        w.append(f"very new (first release {age(first)}): API may still change")
    if r.get("maintainers") == 1:
        w.append("a single maintainer: bus-factor risk")
    if r.get("version") and re.match(r"^0\.", str(r["version"])):
        w.append(f"version {r['version']}: pre-1.0, breaking changes are normal")
    if not r.get("repo_known"):
        w.append("no GitHub repository listed: source and activity could not be checked here")
    if gh.get("github_error"):
        w.append(f"GitHub check skipped: {gh['github_error']}")
    return w


def show(eco: str, r: dict) -> None:
    gh = r.get("gh") or {}
    print(f"\n### {r['name']}  ({eco})  {r.get('summary', '')}")
    print(f"  latest: {r.get('version')}  released {age(r.get('released'))}  | first release {age(r.get('first'))}")
    print(f"  cadence: {r.get('cadence')}")
    print(f"  license: {r.get('license') or 'none declared'}  | requires: {r.get('requires') or 'not stated'}"
          + (f"  | direct dependencies: {r['deps']}" if r.get("deps") is not None else ""))
    if r.get("downloads_month") is not None:
        print(f"  downloads (last month): {r['downloads_month']:,}")
    if r.get("downloads_recent") is not None:
        print(f"  downloads: {r['downloads_recent']:,} recent, {r.get('downloads_total', 0):,} total")
    if r.get("maintainers") is not None:
        print(f"  maintainers on the registry: {r['maintainers']}")
    if gh.get("repo"):
        print(f"  github: {gh['repo']} | stars {gh.get('stars'):,} | forks {gh.get('forks'):,} | open issues+PRs {gh.get('open_issues'):,}"
              f" | last push {age(gh.get('pushed'))} | license {gh.get('gh_license') or '?'}")
    for line in warnings(r):
        print(f"  ! {line}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 3 or sys.argv[1] not in FETCH:
        print(__doc__.strip().split("\n\n")[0])
        print("usage: package_health.py <pypi|npm|crates|go> <name> [<name> ...]")
        return 2
    eco, names = sys.argv[1], sys.argv[2:]
    rows, failed = [], 0
    for n in names:
        try:
            r = FETCH[eco](n)
        except RuntimeError as e:
            print(f"\n### {n}: ERROR - {e}")
            failed += 1
            continue
        if r is None:
            print(f"\n### {n}: not found on {eco} (check the spelling, and beware look-alike names)")
            continue
        show(eco, r)
        rows.append(r)
    if len(rows) > 1:
        print("\n== side by side")
        print(f"  {'name':<22}{'latest':<14}{'released':<16}{'license':<16}{'stars':>9}  warnings")
        for r in rows:
            gh = r.get("gh") or {}
            print(f"  {r['name'][:21]:<22}{str(r.get('version'))[:13]:<14}{age(r.get('released')):<16}{str(r.get('license') or '-')[:15]:<16}"
                  f"{(format(gh['stars'], ',') if gh.get('stars') is not None else '-'):>9}  {len(warnings(r))}")
    print("\nThese are signals, not a verdict. Fit for your project is decided by your requirements, not by popularity.")
    return 1 if failed and not rows else 0


if __name__ == "__main__":
    sys.exit(main())
