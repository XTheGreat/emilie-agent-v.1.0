#!/usr/bin/env python3
"""Accessibility audit of static HTML/CSS and JSX/TSX/Vue markup, mapped to WCAG 2.2 success criteria.

Usage: python a11y_audit.py <file-or-dir> [--level A|AA] [--json] [--top 80]

Combines the contrast, focus-outline, label, alt, language, title, viewport, heading and name checks of the design-ui-ux skill's
ui_audit.py (if that skill is installed next to this one) with deeper checks of its own:
  ARIA     invalid roles, aria-hidden on focusable elements, aria-labelledby/describedby/controls pointing nowhere, redundant roles,
           labels on generic elements, interactive roles without keyboard support
  LINKS    vague link text ("click here", "read more"), target=_blank without rel, # links used as buttons
  FORMS    inputs missing autocomplete hints for personal data, radio/checkbox groups without fieldset/legend, image buttons without alt
  TABLES   data tables without header cells or scope
  MEDIA    video/audio without captions or transcript hints, autoplay, iframes without title, svg images without a name, filename or
           "image of" alt text
  PAGE     landmarks (main/nav), several <main>, repeated nav without labels, missing skip link, blink/marquee, meta refresh
  CSS      animation without a prefers-reduced-motion rule, smooth scrolling, hover-only reveals, tiny fixed touch targets (< 24 px)
  JSX/Vue  <img> without alt, onClick on div/span without role+tabIndex+key handler, positive tabIndex, aria-hidden on interactive tags

Static analysis finds roughly a third of real accessibility problems. It cannot judge reading order, meaningful alt text, focus
management, screen reader announcements, or whether an interaction works with a keyboard. Test those by hand (keyboard only,
200% zoom, a screen reader, reduced motion).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", "vendor", "site-packages", "coverage", "out", "target"}
ROLES = set("""alert alertdialog application article banner button cell checkbox columnheader combobox complementary contentinfo definition dialog directory document
feed figure form grid gridcell group heading img link list listbox listitem log main marquee math menu menubar menuitem menuitemcheckbox menuitemradio navigation none note
option presentation progressbar radio radiogroup region row rowgroup rowheader scrollbar search searchbox separator slider spinbutton status switch tab table tablist tabpanel
term textbox timer toolbar tooltip tree treegrid treeitem generic paragraph blockquote caption code deletion emphasis insertion meter strong subscript superscript time
doc-abstract doc-acknowledgments doc-afterword doc-appendix doc-backlink doc-biblioentry doc-bibliography doc-biblioref doc-chapter doc-colophon doc-conclusion doc-cover
doc-credit doc-credits doc-dedication doc-endnote doc-endnotes doc-epigraph doc-epilogue doc-errata doc-example doc-footnote doc-foreword doc-glossary doc-glossref doc-index
doc-introduction doc-noteref doc-notice doc-pagebreak doc-pagelist doc-part doc-preface doc-prologue doc-pullquote doc-qna doc-subtitle doc-tip doc-toc""".split())
FOCUSABLE = {"a", "button", "input", "select", "textarea", "summary"}
INTERACTIVE_ROLES = {"button", "link", "checkbox", "radio", "switch", "tab", "menuitem", "option", "slider", "textbox", "combobox", "treeitem"}
VAGUE = re.compile(r"^(click here|here|read more|more|learn more|link|this link|click|details|info|continue|go|see more|more info)\.?$", re.I)
AUTOCOMPLETE_TYPES = {"email": "email", "tel": "tel", "password": "current-password"}
NAME_HINT = re.compile(r"(first.?name|last.?name|full.?name|given|family|address|street|city|zip|postal|country|phone|mobile|email|username|birth|card)", re.I)

# keyword -> WCAG success criterion (level)
SC_MAP = [
    (r"autocomplete", "1.3.5 Identify Input Purpose (AA)"),
    (r"caption|autoplay|<video>|<audio>|transcript", "1.2.x Time-based Media / 1.4.2 Audio Control"),
    (r"refresh|blink|marquee|moving", "2.2.1 / 2.2.2 Timing, Pause-Stop-Hide (A)"),
    (r"aria-hidden|focusable|keyboard|clickable|onclick|tabindex|key handler|hover-only", "2.1.1 Keyboard (A) / 2.4.3 Focus Order"),
    (r"contrast", "1.4.3 Contrast (AA)"),
    (r"zoom|viewport", "1.4.4 Resize Text (AA)"),
    (r"alt|<img>|image|svg", "1.1.1 Non-text Content (A)"),
    (r"fieldset|legend|radio group", "1.3.1 Info and Relationships (A)"),
    (r"table|header cell", "1.3.1 Info and Relationships (A)"),
    (r"landmark|<main>|skip link|<nav>", "2.4.1 Bypass Blocks (A) / 1.3.1"),
    (r"link text|vague|click here|read more|link used as a button", "2.4.4 Link Purpose (A)"),
    (r"outline|focus visible|:focus", "2.4.7 Focus Visible (AA)"),
    (r"reduced-motion|animation|transition|smooth", "2.3.3 / 2.2.2 Animation and Motion"),
    (r"target size|touch|24 px|24x24|fixed (width|height)", "2.5.8 Target Size (Minimum) (AA)"),
    (r"heading|<h\d>|<h1>", "1.3.1 Info and Relationships (A) / 2.4.6 Headings and Labels"),
    (r"label|placeholder|aria-labelledby|aria-describedby", "3.3.2 Labels or Instructions (A) / 1.3.1"),
    (r"lang|language tag", "3.1.1 Language of Page (A)"),
    (r"<title>|page has no", "2.4.2 Page Titled (A)"),
    (r"accessible name|role|aria-label|duplicate id|iframe", "4.1.2 Name, Role, Value (A)"),
    (r"hover", "1.4.13 Content on Hover or Focus (AA)"),
    (r"font-size|text under|fixed in px", "1.4.4 Resize Text / 1.4.12 Text Spacing (AA)"),
    (r"target=\"_blank\"|noopener", "3.2.5 Change on Request (AAA) / security"),
    (r"accesskey", "2.1.4 Character Key Shortcuts (A)"),
]


def sc_for(msg: str) -> str:
    m = msg.lower()
    for rx, sc in SC_MAP:
        if re.search(rx, m):
            return sc
    return ""


def load_ui_audit():
    here = Path(__file__).resolve()
    for cand in (here.parents[2] / "design-ui-ux" / "scripts" / "ui_audit.py", here.parent / "ui_audit.py"):
        if cand.is_file():
            spec = importlib.util.spec_from_file_location("ui_audit_shared", cand)
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
                return mod
            except Exception:
                return None
    return None


class Extra(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.f: list[dict] = []
        self.ids: set[str] = set()
        self.refs: list[tuple[int, str, str]] = []
        self.mains = 0
        self.navs: list[tuple[int, bool]] = []
        self.first_link: tuple[str, str] | None = None
        self.radios: dict[str, list[int]] = {}
        self.in_fieldset = 0
        self.stack: list[dict] = []
        self.tables: list[dict] = []
        self.media: list[dict] = []
        self.has_main_role = False
        self.has_skip = False
        self.links_seen = 0

    def add(self, sev, line, msg, why):
        self.f.append({"severity": sev, "line": line, "finding": msg, "why": why})

    def handle_starttag(self, tag, attrs):
        a = {k: (v if v is not None else "") for k, v in attrs}
        line = self.getpos()[0]
        if a.get("id"):
            self.ids.add(a["id"])
        for k in ("aria-labelledby", "aria-describedby", "aria-controls", "aria-owns"):
            if a.get(k):
                for rid in a[k].split():
                    self.refs.append((line, k, rid))
        role = a.get("role", "").strip().lower()
        if role:
            for r in role.split():
                if r not in ROLES:
                    self.add("WARN", line, f"invalid ARIA role '{r}'", "unknown roles are ignored by assistive technology; use a valid role or remove it")
            if tag == "button" and role == "button" or tag == "a" and role == "link" and "href" in a or tag == "nav" and role == "navigation" or tag == "main" and role == "main":
                self.add("INFO", line, f"redundant role '{role}' on <{tag}>", "native elements already expose this role; remove the attribute")
            if role in INTERACTIVE_ROLES and tag not in FOCUSABLE and "tabindex" not in a:
                self.add("WARN", line, f"role={role} on <{tag}> is not keyboard focusable (no tabindex)", "interactive roles need tabindex=0 and key handlers; prefer a native element")
            if role == "main":
                self.has_main_role = True
        if a.get("aria-hidden", "").lower() == "true":
            if tag in FOCUSABLE or (a.get("tabindex", "").lstrip("-").isdigit() and int(a["tabindex"]) >= 0):
                self.add("WARN", line, f"aria-hidden=true on focusable <{tag}>", "keyboard users can focus something screen readers cannot see; remove aria-hidden or make it inert/non-focusable")
        if "aria-label" in a and tag in ("div", "span", "p", "b", "i", "strong", "em") and not role:
            self.add("INFO", line, f"aria-label on a generic <{tag}> with no role", "the label is ignored by most screen readers on generic elements; add a role or use a native element")
        if tag == "a":
            self.links_seen += 1
            href = a.get("href", "")
            if self.first_link is None:
                self.first_link = (href, a.get("class", ""))
                if href.startswith("#") and len(href) > 1:
                    self.has_skip = True
            if a.get("target") == "_blank" and "noopener" not in a.get("rel", "") and "noreferrer" not in a.get("rel", ""):
                self.add("INFO", line, 'target="_blank" without rel="noopener"', "new-tab links should also warn users; add rel=noopener noreferrer")
            if href in ("#", "") and ("onclick" in a or a.get("role") == "button"):
                self.add("INFO", line, "link used as a button (href='#' with a click handler)", "use <button type=button> so it is a button for keyboard and screen reader users")
        if tag == "input":
            t = a.get("type", "text").lower()
            if t == "image" and not a.get("alt"):
                self.add("WARN", line, "<input type=image> without alt", "image buttons need alt text naming the action")
            if t == "radio":
                self.radios.setdefault(a.get("name", ""), []).append(0 if self.in_fieldset or role == "radiogroup" else 1)
            if a.get("autocomplete", "").lower() == "off" and t in ("email", "tel", "password"):
                self.add("INFO", line, "autocomplete=off on a personal-data field", "breaks password managers and autofill; users with motor or memory disabilities rely on them")
            elif "autocomplete" not in a and (t in AUTOCOMPLETE_TYPES or NAME_HINT.search(a.get("name", "") + a.get("id", ""))) and t not in ("checkbox", "radio", "hidden", "submit", "button", "file"):
                self.add("INFO", line, f"<input {t}> without an autocomplete attribute", "add autocomplete (email, name, tel, street-address, new-password ...) so browsers can fill it (WCAG 1.3.5)")
        if tag == "fieldset":
            self.in_fieldset += 1
        if tag == "table":
            self.tables.append({"line": line, "th": 0, "role": role, "scoped": 0, "cols": 0})
            self.stack.append({"tag": "table"})
        if tag == "th" and self.tables:
            self.tables[-1]["th"] += 1
            if a.get("scope"):
                self.tables[-1]["scoped"] += 1
        if tag in ("video", "audio"):
            self.media.append({"tag": tag, "line": line, "track": False, "autoplay": "autoplay" in a, "muted": "muted" in a, "controls": "controls" in a})
        if tag == "track" and self.media and a.get("kind", "subtitles") in ("captions", "subtitles", "descriptions"):
            self.media[-1]["track"] = True
        if tag == "iframe" and not a.get("title", "").strip() and not a.get("aria-label") and a.get("aria-hidden") != "true":
            self.add("WARN", line, "<iframe> without a title", "screen reader users cannot tell what the frame contains")
        if tag == "svg":
            if (role == "img" or "aria-label" in a or "aria-labelledby" in a) and not (a.get("aria-label") or a.get("aria-labelledby")):
                self.stack.append({"tag": "svg", "line": line, "named": False})
            elif role == "img" and not a.get("aria-label"):
                pass
        if tag == "title" and self.stack and self.stack[-1].get("tag") == "svg":
            self.stack[-1]["named"] = True
        if tag == "img":
            alt = a.get("alt", "")
            if re.search(r"\.(png|jpe?g|gif|svg|webp|bmp)$", alt.strip(), re.I) or re.match(r"^(image|img|photo|picture|graphic|icon)( of| for)?\b", alt.strip(), re.I) and len(alt) < 14:
                self.add("INFO", line, f'alt text looks like a placeholder: "{alt[:40]}"', "alt should describe purpose or content; use alt=\"\" for decorative images (avoid 'image of ...')")
        if tag == "main":
            self.mains += 1
        if tag == "nav":
            self.navs.append((line, bool(a.get("aria-label") or a.get("aria-labelledby"))))
        if tag in ("marquee", "blink"):
            self.add("WARN", line, f"<{tag}> element", "moving or blinking content cannot be paused (WCAG 2.2.2)")
        if tag == "meta" and a.get("http-equiv", "").lower() == "refresh" and re.match(r"\s*[1-9]", a.get("content", "")):
            self.add("WARN", line, "meta refresh redirect or reload", "automatic page refresh disorients users; use a server redirect or let users control it")
        if tag == "html" and a.get("lang") and not re.fullmatch(r"[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*", a["lang"].strip()):
            self.add("WARN", line, f"lang value '{a['lang']}' is not a valid language tag", "use a BCP 47 tag such as en, id or pt-BR")
        if a.get("accesskey"):
            self.add("INFO", line, "accesskey used", "access keys conflict with browser and assistive-technology shortcuts")
        if tag in ("div", "span", "p") and any(k in a for k in ("onmouseover", "onmouseenter")) and not any(k in a for k in ("onfocus", "onkeydown", "tabindex")):
            self.add("WARN", line, "hover-only interaction (onmouseover without focus equivalent)", "keyboard and touch users never trigger it; add focus handling or use a native control")
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.stack.append({"tag": tag, "line": line, "text": ""})

    def handle_data(self, data):
        for s in self.stack:
            if "text" in s:
                s["text"] += data
        if self.stack and self.stack[-1].get("tag") == "a":
            self.stack[-1]["text"] += data

    def handle_endtag(self, tag):
        if tag == "fieldset" and self.in_fieldset:
            self.in_fieldset -= 1
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i].get("tag") == tag:
                    s = self.stack.pop(i)
                    if not s["text"].strip():
                        self.add("WARN", s["line"], f"empty <{tag}>", "empty headings are announced as headings with no content; remove them")
                    break
        if tag == "svg" and self.stack and self.stack[-1].get("tag") == "svg":
            s = self.stack.pop()
            if not s["named"]:
                self.add("WARN", s["line"], "<svg role=img> with no accessible name", "add a <title>, aria-label or aria-labelledby (or aria-hidden=true if decorative)")
        if tag == "table" and self.stack and self.stack[-1].get("tag") == "table":
            self.stack.pop()

    def finish(self, fragment: bool):
        for line, k, rid in self.refs:
            if rid not in self.ids:
                self.add("WARN", line, f"{k} references missing id '{rid}'", "the relationship is broken; the name/description is lost")
        for t in self.tables:
            if t["th"] == 0 and t["role"] not in ("presentation", "none") and t["line"]:
                self.add("INFO", t["line"], "<table> without header cells (<th>)", "data tables need <th> (with scope for complex tables); use CSS layout instead of tables for layout")
        for name, flags in self.radios.items():
            if len(flags) > 1 and all(flags):
                self.add("INFO", 1, f"radio group '{name or '(unnamed)'}' is not wrapped in <fieldset>/<legend> or role=radiogroup", "group related options and give the group a name")
        for m in self.media:
            if not m["track"]:
                self.add("WARN" if m["tag"] == "video" else "INFO", m["line"], f"<{m['tag']}> without a captions/subtitles <track>", "provide captions (or a transcript) for audio content")
            if m["autoplay"] and not m["muted"]:
                self.add("WARN", m["line"], f"<{m['tag']}> autoplays with sound", "audio that starts automatically blocks screen readers; require a user action or mute it (WCAG 1.4.2)")
            if m["tag"] == "video" and not m["controls"]:
                self.add("INFO", m["line"], "<video> without controls", "users must be able to pause and control playback")
        if not fragment:
            if self.mains == 0 and not self.has_main_role:
                self.add("INFO", 1, "no <main> landmark", "add <main> so users can jump to the content (WCAG 2.4.1 / 1.3.1)")
            if self.mains > 1:
                self.add("WARN", 1, f"{self.mains} <main> elements", "a page has one main landmark")
            if len(self.navs) > 1 and sum(1 for _, labelled in self.navs if not labelled) > 1:
                self.add("INFO", 1, "several <nav> landmarks without distinguishing labels", "label each (aria-label='Primary', 'Footer') so users can tell them apart")
            if self.links_seen > 4 and not self.has_skip:
                self.add("INFO", 1, "no skip link at the start of the page", "add a first link to #main (visible on focus) to bypass repeated navigation (WCAG 2.4.1)")


def jsx_checks(text: str, rel: str) -> list[dict]:
    out = []

    def add(sev, ln, msg, why):
        out.append({"severity": sev, "where": f"{rel}:{ln}", "finding": msg, "why": why})
    for m in re.finditer(r"<img\b(?![^>]*\balt\s*=)[^>]*>", text, re.S):
        add("WARN", text.count("\n", 0, m.start()) + 1, "<img> without alt", "add alt text, or alt=\"\" if decorative")
    for m in re.finditer(r"<(div|span|li|td|p|section)\b[^>]*\bon(Click|click|@click)\s*=[^>]*>", text, re.S):
        tag = m.group(0)
        if not re.search(r"\brole\s*=", tag) or not re.search(r"\btabIndex\s*=|\btabindex\s*=", tag) or not re.search(r"onKey(Down|Up|Press)|@keydown|@keyup", tag):
            add("WARN", text.count("\n", 0, m.start()) + 1, f"clickable <{m.group(1)}> without role, tabIndex and key handler", "not operable by keyboard; use <button> or <a href>")
    for m in re.finditer(r"\btabIndex\s*=\s*\{?\s*[\"']?([1-9]\d*)", text):
        add("WARN", text.count("\n", 0, m.start()) + 1, f"positive tabIndex ({m.group(1)})", "overrides natural tab order; use 0 or -1")
    for m in re.finditer(r"<(button|a|input|select|textarea)\b[^>]*\baria-hidden\s*=\s*[\"'{]+true", text, re.S):
        add("WARN", text.count("\n", 0, m.start()) + 1, f"aria-hidden=true on <{m.group(1)}>", "focusable content hidden from screen readers")
    for m in re.finditer(r"<(button|a)\b([^>]*)>\s*(<(?:svg|i|img|Icon)\b[^>]*/?>(?:</(?:svg|i)>)?)\s*</\1>", text, re.S):
        if not re.search(r"aria-label|aria-labelledby|title=", m.group(2)) and "alt=" not in m.group(3):
            add("WARN", text.count("\n", 0, m.start()) + 1, f"icon-only <{m.group(1)}> with no accessible name", "add aria-label or visible text")
    for m in re.finditer(r"<(a)\b([^>]*)>\s*(click here|here|read more|more|learn more)\s*</a>", text, re.I | re.S):
        add("INFO", text.count("\n", 0, m.start()) + 1, f"vague link text '{m.group(3)}'", "link text should make sense out of context")
    for m in re.finditer(r"<input\b(?![^>]*(aria-label|aria-labelledby|\bid\s*=|type\s*=\s*[\"'](hidden|submit|button)))[^>]*>", text, re.S):
        add("INFO", text.count("\n", 0, m.start()) + 1, "<input> with no id, aria-label or aria-labelledby", "associate a <label> (htmlFor/for) or name the control")
    return out


def css_extra(text: str, rel: str) -> list[dict]:
    out = []

    def add(sev, ln, msg, why):
        out.append({"severity": sev, "where": f"{rel}:{ln}", "finding": msg, "why": why})
    has_reduce = bool(re.search(r"prefers-reduced-motion", text))
    anim = [m for m in re.finditer(r"\b(animation|transition)(-name|-duration)?\s*:\s*[^;{}]*\d+m?s|scroll-behavior\s*:\s*smooth", text)]
    if anim and not has_reduce:
        add("INFO", text.count("\n", 0, anim[0].start()) + 1, f"{len(anim)} animation/transition/smooth-scroll rule(s) and no prefers-reduced-motion rule in this file", "provide a reduced-motion alternative: @media (prefers-reduced-motion: reduce) { * { animation: none; transition: none; scroll-behavior: auto } }")
    for m in re.finditer(r"([^{}]*?(?:\bbutton\b|\ba\b|\binput\b|\.btn\b|\[role=[\"']?button)[^{}]*)\{([^{}]*)\}", text):
        body = m.group(2)
        for prop in ("width", "height"):
            mm = re.search(rf"(?<![\w-]){prop}\s*:\s*(\d+(?:\.\d+)?)px", body)
            if mm and float(mm.group(1)) < 24 and not re.search(r"min-" + prop, body) and "display: none" not in body:
                add("INFO", text.count("\n", 0, m.start()) + 1, f"fixed {prop} of {mm.group(1)}px on a control ({m.group(1).strip()[:40]})", "touch targets should be at least 24x24 CSS px (WCAG 2.5.8) and ideally 44x44")
                break
    for m in re.finditer(r"([^{}@]+):hover\s*(?:[^{}]*)\{[^{}]*\b(display\s*:\s*(block|flex)|visibility\s*:\s*visible|opacity\s*:\s*1)\b", text):
        sel = m.group(1).strip().split(",")[-1].strip()
        if sel and sel not in text.replace(sel + ":hover", "").replace(sel + ":focus", "|") and f"{sel}:focus" not in text:
            add("INFO", text.count("\n", 0, m.start()) + 1, f"content revealed on :hover only ({sel[:40]})", "add the same rule for :focus/:focus-within so keyboard users can reach it")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target")
    ap.add_argument("--level", choices=["A", "AA"], default="AA")
    ap.add_argument("--top", type=int, default=80)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    t = Path(a.target)
    if not t.exists():
        print(f"error: {a.target} not found", file=sys.stderr)
        return 2
    ui = load_ui_audit()
    paths = [t] if t.is_file() else []
    if t.is_dir():
        for dp, dn, fn in os.walk(t):
            dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.startswith(".")]
            paths += [Path(dp) / f for f in fn if Path(f).suffix.lower() in {".html", ".htm", ".css", ".jsx", ".tsx", ".vue", ".svelte", ".erb", ".twig"} and not f.endswith(".min.css")]
    findings: list[dict] = []
    for p in paths[:400]:
        rel = p.relative_to(t).as_posix() if t.is_dir() else p.name
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        ext = p.suffix.lower()
        if ext in (".html", ".htm", ".erb", ".twig"):
            if ui:
                findings += ui.audit_html(text, rel)
            ex = Extra()
            try:
                ex.feed(text)
                ex.close()
            except Exception:
                pass
            ex.finish(fragment="<html" not in text.lower())
            findings += [{"severity": f["severity"], "where": f"{rel}:{f['line']}", "finding": f["finding"], "why": f["why"]} for f in ex.f]
            for m in re.finditer(r"<style[^>]*>(.*?)</style>", text, re.S | re.I):
                findings += css_extra(m.group(1), rel + " <style>")
        elif ext == ".css":
            if ui:
                findings += ui.audit_css(text, rel)
            findings += css_extra(text, rel)
        else:
            findings += jsx_checks(text, rel)
    seen, uniq = set(), []
    for f in findings:
        k = (f["where"], f["finding"])
        if k not in seen:
            seen.add(k)
            f["wcag"] = sc_for(f["finding"] + " " + f.get("why", ""))
            uniq.append(f)
    order = {"WARN": 0, "INFO": 1}
    uniq.sort(key=lambda x: (order[x["severity"]], x["where"]))
    w = sum(1 for f in uniq if f["severity"] == "WARN")
    if a.json:
        print(json.dumps({"files": len(paths), "warnings": w, "notes": len(uniq) - w, "shared_ui_audit": bool(ui), "findings": uniq}, indent=2))
        return 0
    print(f"Files audited: {len(paths)}" + ("" if ui else "  (design-ui-ux/ui_audit.py not found: contrast and basic HTML checks skipped)"))
    print(f"{w} warning(s), {len(uniq) - w} note(s)\n")
    for f in uniq[: a.top]:
        print(f"[{f['severity']}] {f['where']}: {f['finding']}" + (f"   [WCAG {f['wcag']}]" if f["wcag"] else "") + f"\n        why: {f['why']}")
    if len(uniq) > a.top:
        print(f"\n... {len(uniq) - a.top} more (use --top or --json)")
    cats = Counter(f["wcag"].split(" (")[0] for f in uniq if f["wcag"])
    if cats:
        print("\nBy WCAG criterion: " + ", ".join(f"{k} x{v}" for k, v in cats.most_common(8)))
    print("\nAutomated checks find roughly a third of real problems. Still test: keyboard-only use (tab order, visible focus, no traps), 200% zoom and 320 px width,")
    print("a screen reader on the main task, reduced motion, high contrast mode, meaningful alt text and link text, error messages and focus management in dynamic UI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
