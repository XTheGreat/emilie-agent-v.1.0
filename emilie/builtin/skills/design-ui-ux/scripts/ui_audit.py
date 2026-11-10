#!/usr/bin/env python3
"""Audit CSS colors and basic HTML structure for usability and accessibility.

Usage:
  python ui_audit.py <file-or-dir> [--json]          audit .css and .html files
  python ui_audit.py --pair <fg> <bg> [--large]      contrast of two colors (+ a suggestion)

Checks (WCAG 2.1 AA thresholds: 4.5:1 normal text, 3:1 large text and UI parts):
  CSS   text/background contrast per rule (resolves simple var(--x) tokens,
        light and dark schemes), outline removed without a visible replacement,
        tiny font sizes, fixed-pixel body text.
  HTML  missing lang/title/viewport, zoom disabled, images without alt, form
        controls without a label, buttons/links without a name, headings that
        skip levels, clickable div/span without role and tabindex, positive
        tabindex, duplicate ids.

Read-only, stdlib only. Not a substitute for testing with a keyboard, a screen
reader and real users. Limits: static files only (no JSX/Vue templates, no
computed or inherited styles, no images behind text, no hover/focus states
except those written in the same rule).
"""
from __future__ import annotations

import argparse
import colorsys
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", "vendor", "site-packages", "coverage"}
NAMED = {
    "white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0), "green": (0, 128, 0), "blue": (0, 0, 255),
    "gray": (128, 128, 128), "grey": (128, 128, 128), "silver": (192, 192, 192), "yellow": (255, 255, 0),
    "orange": (255, 165, 0), "navy": (0, 0, 128), "teal": (0, 128, 128), "purple": (128, 0, 128), "maroon": (128, 0, 0),
    "lightgray": (211, 211, 211), "lightgrey": (211, 211, 211), "darkgray": (169, 169, 169), "darkgrey": (169, 169, 169),
    "lime": (0, 255, 0), "aqua": (0, 255, 255), "cyan": (0, 255, 255), "fuchsia": (255, 0, 255), "magenta": (255, 0, 255),
}


# ------------------------------------------------------------------ colors
def parse_color(s: str):
    """Return (r, g, b, a) or None."""
    s = s.strip().lower()
    if s in NAMED:
        return (*NAMED[s], 1.0)
    if s == "transparent":
        return (0, 0, 0, 0.0)
    m = re.fullmatch(r"#([0-9a-f]{3,8})", s)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) in (6, 8):
            r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
            a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
            return (r, g, b, a)
        return None
    m = re.fullmatch(r"rgba?\(\s*([^)]+)\)", s)
    if m:
        parts = [p for p in re.split(r"[\s,/]+", m.group(1).strip()) if p]
        if len(parts) >= 3:
            def ch(v):
                return round(float(v[:-1]) * 2.55) if v.endswith("%") else float(v)
            try:
                a = 1.0
                if len(parts) >= 4:
                    a = float(parts[3][:-1]) / 100 if parts[3].endswith("%") else float(parts[3])
                return (ch(parts[0]), ch(parts[1]), ch(parts[2]), a)
            except ValueError:
                return None
    m = re.fullmatch(r"hsla?\(\s*([^)]+)\)", s)
    if m:
        parts = [p for p in re.split(r"[\s,/]+", m.group(1).strip()) if p]
        if len(parts) >= 3:
            try:
                h = float(parts[0].replace("deg", "")) % 360 / 360
                sat = float(parts[1].rstrip("%")) / 100
                lig = float(parts[2].rstrip("%")) / 100
                a = 1.0
                if len(parts) >= 4:
                    a = float(parts[3][:-1]) / 100 if parts[3].endswith("%") else float(parts[3])
                r, g, b = colorsys.hls_to_rgb(h, lig, sat)
                return (r * 255, g * 255, b * 255, a)
            except ValueError:
                return None
    return None


def lum(rgb) -> float:
    def f(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb[:3]
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b) -> float:
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def over(fg, bg):
    a = fg[3]
    return tuple(fg[i] * a + bg[i] * (1 - a) for i in range(3))


def suggest(fg, bg, target):
    """Move the foreground's lightness away from the background until it passes."""
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in fg[:3]))
    direction = -1 if lum(bg) > 0.5 else 1
    for _ in range(100):
        l = min(1.0, max(0.0, l + direction * 0.01))
        r, g, b = (round(c * 255) for c in colorsys.hls_to_rgb(h, l, s))
        if ratio((r, g, b), bg) >= target:
            return "#%02x%02x%02x" % (r, g, b)
        if l in (0.0, 1.0):
            break
    return None


# --------------------------------------------------------------------- CSS
def tokenize_css(css: str):
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    stack: list[str] = []
    buf = ""
    i = 0
    while i < len(css):
        ch = css[i]
        if ch == "{":
            stack.append(buf.strip())
            buf = ""
            body_start = i + 1
            # find the end of this block when it contains no nested block (a rule)
            j = css.find("}", body_start)
            k = css.find("{", body_start)
            if j != -1 and (k == -1 or j < k):
                yield (list(stack[:-1]), stack[-1], css[body_start:j])
                stack.pop()
                i = j
        elif ch == "}":
            if stack:
                stack.pop()
            buf = ""
        else:
            buf += ch
        i += 1


def decls(body: str) -> dict[str, str]:
    out = {}
    for part in re.split(r";(?![^()]*\))", body):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def is_dark(ctx: list[str], selector: str) -> bool:
    text = " ".join(ctx) + " " + selector
    return bool(re.search(r"prefers-color-scheme\s*:\s*dark|\[data-theme=[\"']?dark|\.dark\b|\.theme-dark|data-bs-theme=[\"']?dark", text, re.I))


def audit_css(text: str, name: str) -> list[dict]:
    out: list[dict] = []
    rules = list(tokenize_css(text))
    vars_by_scheme: dict[bool, dict[str, str]] = {False: {}, True: {}}
    for ctx, sel, body in rules:
        if sel.startswith("@"):
            continue
        for k, v in decls(body).items():
            if k.startswith("--"):
                vars_by_scheme[is_dark(ctx, sel)][k] = v

    def resolve(val: str, dark: bool, depth=0):
        m = re.fullmatch(r"var\(\s*(--[\w-]+)\s*(?:,\s*(.+))?\)", val.strip())
        if not m or depth > 5:
            return val
        v = vars_by_scheme[dark].get(m.group(1)) or vars_by_scheme[False].get(m.group(1)) or m.group(2)
        return resolve(v, dark, depth + 1) if v else val

    def add(sev, where, msg, why):
        out.append({"severity": sev, "where": f"{name} {where}", "finding": msg, "why": why})

    for ctx, sel, body in rules:
        if sel.startswith("@") or not body.strip():
            continue
        d = decls(body)
        base_dark = is_dark(ctx, sel)
        uses_var = "var(" in body
        for dark in ([base_dark] if base_dark or not (uses_var and vars_by_scheme[True]) else [False, True]):
            check_colors(sel, d, dark, base_dark, resolve, add)
        _check_other(sel, d, body, add)
    return out


def check_colors(sel, d, dark, base_dark, resolve, add):
    fg_raw = d.get("color")
    bg_raw = d.get("background-color") or (d.get("background") if d.get("background") and not re.search(r"gradient|url\(", d["background"], re.I) else None)
    if bg_raw and d.get("background") == bg_raw and not d.get("background-color"):
        first = re.split(r"\s+(?![^()]*\))", bg_raw)
        bg_raw = next((t for t in first if parse_color(resolve(t, dark))), None)
    if fg_raw and bg_raw:
        fg, bg = parse_color(resolve(fg_raw, dark)), parse_color(resolve(bg_raw, dark))
        if fg and bg:
            if bg[3] < 1:
                bg = (*over(bg, (255, 255, 255) if not dark else (0, 0, 0)), 1.0)
            eff = (*over(fg, bg), 1.0) if fg[3] < 1 else fg
            fs = d.get("font-size", "")
            px = None
            m = re.match(r"([\d.]+)(px|rem|em|pt)", fs)
            if m:
                px = float(m.group(1)) * {"px": 1, "rem": 16, "em": 16, "pt": 1.333}[m.group(2)]
            bold = d.get("font-weight", "") in ("bold", "600", "700", "800", "900")
            large = bool(px and (px >= 24 or (px >= 18.66 and bold)))
            need = 3.0 if large else 4.5
            r = ratio(eff, bg)
            if r < need:
                sug = suggest(eff, bg, need)
                add("WARN", f"`{sel}`" + (" (dark scheme)" if dark else ""),
                    f"contrast {r:.2f}:1 ({fg_raw} on {bg_raw}), needs {need}:1",
                    "low-contrast text is unreadable for many users and in sunlight" + (f"; try {sug}" if sug else ""))


def _check_other(sel, d, body, add):
    fs = d.get("font-size", "")
    m = re.match(r"([\d.]+)(px|rem|em)", fs)
    if m:
        px = float(m.group(1)) * (1 if m.group(2) == "px" else 16)
        if px < 12 and not re.search(r"(::?before|::?after|sup|sub|caption|small|badge)", sel, re.I):
            add("INFO", f"`{sel}`", f"font-size {fs}", "text under 12px is hard to read; keep body text at 16px or larger")
    if re.search(r"(^|,|\s)(html|body)\b", sel) and re.match(r"[\d.]+px", d.get("font-size", "")):
        add("INFO", f"`{sel}`", f"base font-size fixed in px ({d['font-size']})", "use rem or % so the user's browser font-size setting works")
    outl = d.get("outline", "") + d.get("outline-style", "")
    if re.search(r"(\bnone\b|(^|\s)0(px)?(\s|$))", outl) and re.search(r":focus", sel) and not re.search(r"focus-visible", sel):
        if not any(k in d for k in ("box-shadow", "border", "border-color", "background", "background-color", "text-decoration")):
            add("WARN", f"`{sel}`", "focus outline removed with no replacement", "keyboard users lose track of where they are; style :focus-visible instead")
    if d.get("outline", "").strip() in ("none", "0") and not re.search(r":focus|:hover|:active", sel) and re.search(r"\b(button|a|input|select|textarea|btn)\b", sel):
        if not any(k in d for k in ("box-shadow", "border")):
            add("INFO", f"`{sel}`", "outline removed on a control", "make sure a :focus-visible style exists elsewhere")
    if re.search(r"user-select\s*:\s*none", body) and re.search(r"\b(body|html|p|article|main)\b", sel):
        add("INFO", f"`{sel}`", "text selection disabled", "blocks copying and assistive tools")


# -------------------------------------------------------------------- HTML
class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.findings: list[dict] = []
        self.has_lang = self.has_title = self.has_viewport = False
        self.stack: list[dict] = []
        self.headings: list[tuple[int, int]] = []
        self.ids: dict[str, int] = {}
        self.labels_for: set[str] = set()
        self.controls: list[dict] = []
        self.in_title = False
        self.title_text = ""
        self.h1 = 0

    def add(self, sev, line, msg, why):
        self.findings.append({"severity": sev, "line": line, "finding": msg, "why": why})

    def handle_starttag(self, tag, attrs):
        a = {k: (v if v is not None else "") for k, v in attrs}
        line = self.getpos()[0]
        if tag == "html":
            self.has_lang = bool(a.get("lang", "").strip())
        elif tag == "title":
            self.in_title = True
        elif tag == "meta" and a.get("name", "").lower() == "viewport":
            self.has_viewport = True
            if re.search(r"user-scalable\s*=\s*(no|0)|maximum-scale\s*=\s*1(\.0)?\b", a.get("content", ""), re.I):
                self.add("WARN", line, "viewport blocks zoom", "users with low vision need pinch zoom; remove user-scalable=no / maximum-scale=1")
        if "id" in a:
            self.ids[a["id"]] = self.ids.get(a["id"], 0) + 1
        if tag == "img" and "alt" not in a and a.get("role") not in ("presentation", "none"):
            self.add("WARN", line, "<img> without alt", "screen readers announce the file name; use alt text, or alt=\"\" if decorative")
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append((int(tag[1]), line))
            if tag == "h1":
                self.h1 += 1
        if tag in ("input", "select", "textarea"):
            t = a.get("type", "text").lower()
            if not (tag == "input" and t in ("hidden", "submit", "button", "reset", "image")):
                self.controls.append({"tag": tag, "attrs": a, "line": line, "in_label": any(s["tag"] == "label" for s in self.stack)})
            if tag == "input" and t in ("submit", "button", "reset") and not (a.get("value") or a.get("aria-label")):
                self.add("WARN", line, f"<input type={t}> without a value", "buttons need an accessible name")
        if tag == "label" and a.get("for"):
            self.labels_for.add(a["for"])
        if a.get("tabindex", "").lstrip("-").isdigit() and int(a["tabindex"]) > 0:
            self.add("WARN", line, f"positive tabindex ({a['tabindex']})", "overrides the natural tab order; use 0 or -1 only")
        if tag in ("div", "span", "li", "td") and any(k in a for k in ("onclick", "@click", "v-on:click", "ng-click")):
            if "role" not in a or "tabindex" not in a:
                self.add("WARN", line, f"clickable <{tag}> without role and tabindex", "not reachable or operable by keyboard; use <button> or <a href>")
        if tag == "a" and "href" not in a and "onclick" not in a and not a.get("role"):
            self.add("INFO", line, "<a> without href", "not focusable; use <button> for actions")
        if tag in ("a", "button"):
            self.stack.append({"tag": tag, "attrs": a, "line": line, "text": "", "has_img_alt": False})
        elif tag == "label":
            self.stack.append({"tag": "label", "attrs": a, "line": line, "text": "", "has_img_alt": False})
        elif self.stack and tag == "img" and a.get("alt", "").strip():
            self.stack[-1]["has_img_alt"] = True
        if a.get("autofocus") is not None and "autofocus" in a:
            self.add("INFO", line, "autofocus used", "can disorient screen reader users and scroll the page; use deliberately")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if self.in_title:
            self.title_text += data
        for s in self.stack:
            s["text"] += data

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
            self.has_title = bool(self.title_text.strip())
        if tag in ("a", "button", "label"):
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i]["tag"] == tag:
                    s = self.stack.pop(i)
                    if tag in ("a", "button"):
                        a = s["attrs"]
                        if not (s["text"].strip() or a.get("aria-label", "").strip() or a.get("aria-labelledby") or a.get("title", "").strip() or s["has_img_alt"]):
                            if tag == "a" and "href" not in a:
                                break
                            self.add("WARN", s["line"], f"<{tag}> with no accessible name", "icon-only controls need aria-label or visible text")
                    break

    def finish(self):
        if not self.has_lang:
            self.add("WARN", 1, "<html> has no lang attribute", "screen readers pick the wrong pronunciation without it")
        if not self.has_title:
            self.add("WARN", 1, "page has no <title>", "tab, history and screen reader users depend on it")
        if not self.has_viewport:
            self.add("INFO", 1, "no viewport meta tag", "mobile browsers render a zoomed-out desktop page")
        for c in self.controls:
            a = c["attrs"]
            if not (c["in_label"] or a.get("aria-label", "").strip() or a.get("aria-labelledby") or (a.get("id") and a["id"] in self.labels_for) or a.get("title", "").strip()):
                self.add("WARN", c["line"], f"<{c['tag']}> without a label", "placeholder text is not a label; use <label for> or aria-label" + (" (placeholder present)" if a.get("placeholder") else ""))
        prev = 0
        for lvl, line in self.headings:
            if prev and lvl > prev + 1:
                self.add("INFO", line, f"heading jumps from h{prev} to h{lvl}", "keep levels in order so the outline makes sense")
            prev = lvl
        if self.headings and self.h1 == 0:
            self.add("INFO", self.headings[0][1], "no <h1>", "each page needs one main heading")
        if self.h1 > 1:
            self.add("INFO", 1, f"{self.h1} <h1> elements", "usually one per page")
        for i, n in self.ids.items():
            if n > 1:
                self.add("WARN", 1, f"duplicate id '{i}' ({n}x)", "label links, ARIA references and scripts break on duplicate ids")


def audit_html(text: str, name: str) -> list[dict]:
    p = Page()
    try:
        p.feed(text)
        p.close()
    except Exception as e:  # malformed markup should not crash the audit
        return [{"severity": "INFO", "where": name, "finding": f"could not fully parse ({e})", "why": "audit incomplete"}]
    is_fragment = "<html" not in text.lower()
    p.finish()
    out = []
    for f in p.findings:
        if is_fragment and f["finding"].startswith(("<html>", "page has no <title>", "no viewport")):
            continue
        out.append({"severity": f["severity"], "where": f"{name}:{f['line']}", "finding": f["finding"], "why": f["why"]})
    # inline <style> blocks
    for m in re.finditer(r"<style[^>]*>(.*?)</style>", text, re.S | re.I):
        out += audit_css(m.group(1), name + " <style>")
    return out


# -------------------------------------------------------------------- main
def pair_mode(fg_s: str, bg_s: str, large: bool) -> int:
    fg, bg = parse_color(fg_s), parse_color(bg_s)
    if not fg or not bg:
        print("error: could not parse a color (use #rgb, #rrggbb, rgb(), hsl() or a basic name)", file=sys.stderr)
        return 1
    if bg[3] < 1:
        bg = (*over(bg, (255, 255, 255)), 1.0)
    eff = (*over(fg, bg), 1.0) if fg[3] < 1 else fg
    r = ratio(eff, bg)
    need = 3.0 if large else 4.5
    print(f"contrast {r:.2f}:1")
    print(f"  normal text (4.5): {'pass' if r >= 4.5 else 'FAIL'}")
    print(f"  large text / UI parts (3.0): {'pass' if r >= 3 else 'FAIL'}")
    print(f"  AAA normal (7.0): {'pass' if r >= 7 else 'no'}")
    if r < need:
        s = suggest(eff, bg, need)
        if s:
            print(f"  nearest passing foreground for {need}:1: {s}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?")
    ap.add_argument("--pair", nargs=2, metavar=("FG", "BG"))
    ap.add_argument("--large", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.pair:
        return pair_mode(a.pair[0], a.pair[1], a.large)
    if not a.target:
        ap.print_usage()
        return 1
    t = Path(a.target)
    if not t.exists():
        print(f"error: {a.target} not found", file=sys.stderr)
        return 1
    files = []
    if t.is_file():
        files = [t]
    else:
        for dp, dn, fn in os.walk(t):
            dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.startswith(".")]
            files += [Path(dp) / f for f in fn if Path(f).suffix.lower() in {".css", ".html", ".htm"} and not f.endswith(".min.css")]
    findings: list[dict] = []
    for f in files[:400]:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = f.relative_to(t).as_posix() if t.is_dir() else f.name
        findings += audit_css(text, rel) if f.suffix.lower() == ".css" else audit_html(text, rel)
    if a.json:
        print(json.dumps({"files": len(files), "findings": findings}, indent=2))
        return 0
    print(f"Files audited: {len(files)} (.css/.html)\n")
    order = {"WARN": 0, "INFO": 1}
    for f in sorted(findings, key=lambda x: (order[x["severity"]], x["where"])):
        print(f"[{f['severity']}] {f['where']}: {f['finding']}\n        why: {f['why']}")
    w = sum(1 for f in findings if f["severity"] == "WARN")
    print(f"\n{w} warning(s), {len(findings) - w} note(s). Automated checks find roughly a third of real problems:")
    print("also test with the keyboard only, at 200% zoom, with a screen reader, and with real users.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
