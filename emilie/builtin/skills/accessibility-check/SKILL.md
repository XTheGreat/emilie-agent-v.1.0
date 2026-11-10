---
name: accessibility-check
phase: cek-mutu
description: Audit a web page or UI against WCAG 2.2 AA - run an automated scan of HTML, CSS and JSX/Vue (contrast, labels, alt text, ARIA misuse, landmarks, keyboard operability, motion, target size), then test what automation cannot (keyboard-only, focus management, zoom and reflow, screen reader behavior, forms and errors), and report prioritized, WCAG-mapped findings with concrete fixes. Prefers native HTML over ARIA. Not for designing the interface (design-ui-ux) or general code review (review-code). Triggers - "accessibility", "a11y", "WCAG", "screen reader", "keyboard navigation", "color contrast", "is this accessible", "ARIA", "alt text", "section 508", "ADA compliance".
---

# Accessibility check

**Goal:** find the barriers that stop people with disabilities from using the interface (blind, low vision, color-blind, deaf, motor, cognitive, vestibular), rank them
by impact, and give fixes that work in real browsers and assistive technology.

## Ground rules

1. **Standard and level first.** Default target: WCAG 2.2 level AA (also what most laws reference). Ask if the user needs another level or a specific law (ADA, Section 508,
   EN 301 549, EAA). State what was assessed (pages, states, components, browsers).
2. **Automation finds about a third.** Scanners catch missing alt text, contrast, labels and ARIA errors; they cannot judge meaning, order, keyboard flow, focus handling or
   announcements. Always combine the scan with manual checks of the main user journeys.
3. **Test the real thing.** Prefer running the page and trying keyboard and screen reader use over reasoning from markup. If you cannot run a browser or assistive technology, say so, and
   limit the claims to "static analysis only".
4. **Native HTML first, ARIA last.** `<button>`, `<a href>`, `<label>`, `<nav>`, `<main>`, `<dialog>`, `<details>` come with behavior and semantics. Bad ARIA is worse than none: it overrides correct
   semantics. Use ARIA only where HTML has no equivalent, and implement the full keyboard pattern.
5. **Prioritize by user impact**: barriers that block a task (cannot reach, cannot operate, cannot perceive, cannot understand) come first. Then widespread issues, then polish.
6. **Meaning matters.** A present `alt` is not a good `alt`; a label that exists is not necessarily correct. Check that names, labels, headings and link text make sense out of context.
7. **Do not claim compliance.** Say "no automated or manual failures found in the tested scope", never "fully accessible" or "WCAG compliant". Conformance claims need a full evaluation.
8. **Fix without breaking.** Changes must keep the visual design working and be tested again (keyboard, zoom, reduced motion). Prefer small, native fixes.
9. **Respect privacy and permissions.** Run browsers and tools only with the user's approval; do not install packages or enter credentials; test only pages the user owns or may test.
10. **Be honest about what was not tested** (screen reader and browser combinations, mobile, languages, authenticated areas, dynamic states).

## Procedure

### Step 1 - Define scope

List the pages, components or flows to audit (the main task of the product first: sign up, search, checkout), the states (empty, error, loading, logged in, modal open), the devices and browsers, and the target (WCAG 2.2 AA). Identify the user groups most affected. Find the source: HTML/CSS files, templates, or components (`glob`).

### Step 2 - Automated scan of the source

```
python "<this skill's directory>/scripts/a11y_audit.py" <file-or-folder> [--level AA] [--top 80] [--json]
```

It scans `.html`, `.css`, `.jsx`, `.tsx`, `.vue`, `.svelte`, `.erb` and `.twig` and reports, mapped to WCAG success criteria: contrast per CSS rule (with variable tokens and dark scheme), focus outlines, labels,
alt text, language, title, viewport and zoom, heading order, invalid or redundant ARIA, `aria-hidden` on focusable elements, broken `aria-labelledby` references, vague links, missing captions, autoplay, iframes
without titles, tables without headers, landmarks and skip links, hover-only reveals, tiny fixed targets, motion without a reduced-motion rule, and in JSX/Vue: images without alt, clickable `div`s, positive `tabIndex`,
icon-only buttons. It reuses the `design-ui-ux` skill's `ui_audit.py` when installed. To check one color pair use `ui_audit.py --pair <fg> <bg>`. If the project already has a tool (axe, Lighthouse, pa11y, eslint-plugin-jsx-a11y,
jest-axe), prefer running it too, but only if installed and allowed; do not install packages without asking.

### Step 3 - Verify the scan results

Open each reported element in context. Remove false positives (decorative images with `alt=""`, a label supplied by a wrapper, a skip link provided by the layout). Classify: **Failure** (WCAG criterion not met), **Warning** (likely issue
needing a human decision), **Pass**. Record the WCAG criterion for each.

### Step 4 - Manual tests (the part automation cannot do)

Follow `references/wcag-checklist.md` and run these on each key journey, in a real browser when possible:

1. **Keyboard only**: can every function be reached and operated with Tab, Shift+Tab, Enter, Space, arrows and Esc? Is the focus indicator always visible and not obscured? Is the tab order logical? Any keyboard traps? Do menus, dialogs and
   widgets follow the expected keyboard pattern? Does focus move to a dialog on open and return on close?
2. **Zoom and reflow**: at 200% zoom and at 320 CSS px width, no loss of content or function, no horizontal scrolling (except tables/maps), text spacing adjustable without breakage.
3. **Screen reader**: with NVDA/JAWS (Windows), VoiceOver (macOS/iOS) or TalkBack (Android), do the heading structure, landmarks, links, form labels, errors, tables and dynamic updates make sense when heard? Are status messages announced (live regions)?
4. **Color and contrast**: text 4.5:1 (3:1 large), UI components and focus indicators 3:1, information never by color alone, check dark mode and hover/focus/disabled states.
5. **Forms**: every field has a visible label; required fields and formats are stated before submission; errors are specific, associated with the field, announced, and focus moves to the first error; no unexpected context changes.
6. **Motion and time**: respects `prefers-reduced-motion`; nothing flashes more than 3 times per second; auto-updating or timed content can be paused or extended; no autoplaying audio.
7. **Content**: meaningful alt text, descriptive link and button text, clear headings, plain language, page language set, abbreviations or jargon explained, consistent navigation.
8. **Touch and pointer**: targets at least 24x24 CSS px (44 recommended), no path-only gestures, dragging has an alternative, hover/focus content is dismissible and persistent.

### Step 5 - Report

Use the template in `references/wcag-checklist.md`: scope and method, summary (counts by severity), findings ordered by user impact with: ID, WCAG criterion and level, location, what fails, who is affected, evidence (steps or output), severity (Blocker, Major, Minor), and
a specific fix. Include what passed, what was not tested, and the manual test log (browser, AT, versions).

### Step 6 - Fix and retest (when asked)

Apply fixes from `references/fixes.md` one class at a time (labels, names, keyboard, focus, contrast, landmarks, motion). After each batch rerun the scanner, then repeat the keyboard, zoom and screen reader checks on the affected flows. Add regression protection
where the project allows it (eslint-plugin-jsx-a11y, axe in component tests, a CI check). Show before and after.

## Definition of done

- [ ] The standard and level, pages, states and devices in scope are written down.
- [ ] The scanner ran on all relevant source, and every finding was verified or dismissed with a reason.
- [ ] The main journeys were tested by keyboard, at 200% zoom/320 px, and (if possible) with a screen reader; or the limits are stated.
- [ ] Contrast, forms and errors, motion, content quality and target sizes were checked.
- [ ] Each finding has a WCAG criterion, location, affected users, evidence, severity and a concrete fix.
- [ ] No compliance claim beyond the tested scope; untested areas are listed.
- [ ] Fixes (if made) were retested, did not break the design, and use native HTML where possible.

## Pitfalls

- **Relying on the scanner alone**, or on an overlay widget that promises compliance. Overlays do not fix the underlying markup.
- **ARIA everywhere.** `div role="button"` without keyboard handling, `aria-label` that contradicts visible text, roles that remove native semantics.
- **Removing focus outlines** for looks, with no replacement.
- **Placeholder-as-label**, icon-only buttons with no name, and links that say "click here".
- **Contrast checked only for body text**, not for placeholders, disabled states, focus rings, icons, charts or text over images.
- **Color-only status** (red/green) with no text or icon.
- **Modals without focus management**: focus stays behind, no Esc, no return of focus.
- **Dynamic updates in silence**: toasts, validation errors and results loaded by script that screen readers never announce.
- **Ignoring zoom and reflow**: fixed pixel layouts and `user-scalable=no`.
- **Testing only the happy state** (not errors, empty, loading, logged in, mobile).
- **Declaring "compliant".** Report evidence and scope instead.

## Hand-offs

| Next | Load |
|---|---|
| redesign flows, components, tokens | `design-ui-ux` |
| implement the fixes | `build-feature` |
| review the fix | `review-code` |
| tests that keep it fixed | `write-tests` |
| performance impact of the fixes | `profile-performance` |
| CI check for accessibility | `setup-ci-cd` |
