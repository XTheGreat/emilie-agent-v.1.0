# Accessibility fixes: patterns that work

Prefer native elements. Test each fix with keyboard, zoom and, if possible, a screen reader.

## Page basics

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">   <!-- never user-scalable=no -->
  <title>Orders - Acme</title>                                              <!-- unique and descriptive; update on route change in SPAs -->
</head>
<body>
  <a class="skip-link" href="#main">Skip to content</a>
  <header>...</header>
  <nav aria-label="Primary">...</nav>
  <main id="main" tabindex="-1">...</main>
  <footer>...</footer>
</body>
```
```css
.skip-link { position: absolute; left: -999px; }
.skip-link:focus { left: 1rem; top: 1rem; background: #fff; color: #000; padding: .5rem 1rem; z-index: 1000; }
.visually-hidden { position: absolute !important; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap; }
```

## Names for controls

```html
<button type="button" aria-label="Close dialog"><svg aria-hidden="true" focusable="false">...</svg></button>   <!-- icon-only button -->
<button type="button"><svg aria-hidden="true">...</svg> <span>Save</span></button>                            <!-- visible text is best -->
<a href="/report.pdf">Annual report (PDF, 2 MB)</a>                                                           <!-- not "click here" -->
```
The accessible name should include the visible label (2.5.3). Avoid `title` as the only name.

## Images

```html
<img src="chart.png" alt="Sales rose 20% from January to June 2026">        <!-- purpose or content -->
<img src="divider.png" alt="">                                              <!-- decorative -->
<svg role="img" aria-labelledby="t"><title id="t">Search</title>...</svg>   <!-- meaningful inline SVG -->
<svg aria-hidden="true" focusable="false">...</svg>                          <!-- decorative SVG -->
```
Complex charts: a short alt plus a nearby data table or long description.

## Forms

```html
<label for="email">Email address</label>
<input id="email" name="email" type="email" autocomplete="email" required aria-describedby="email-help email-err">
<p id="email-help">We only use it to send your receipt.</p>
<p id="email-err" role="alert" hidden>Enter an address like name@example.com</p>

<fieldset>
  <legend>Delivery speed</legend>
  <label><input type="radio" name="speed" value="std"> Standard</label>
  <label><input type="radio" name="speed" value="fast"> Express</label>
</fieldset>
```
- Visible labels always; placeholders are hints, not labels.
- On submit with errors: list errors in a summary at the top (`role="alert"` or move focus to it), link each to its field, set `aria-invalid="true"` on the fields, keep the user's input.
- Use `autocomplete` tokens (name, email, tel, street-address, postal-code, new-password, current-password, one-time-code).
- Allow paste into password fields; do not require remembering or transcribing for login (3.3.8).

## Buttons, links and clickable things

- Navigation = `<a href>`; action = `<button type="button">`. Never `<div onclick>`.
- If a custom element is unavoidable: `role="button" tabindex="0"` and handle Enter and Space, and style `:focus-visible`.

## Focus

```css
:focus-visible { outline: 2px solid #0b5bd3; outline-offset: 2px; }     /* never outline: none without a replacement */
```
- Do not use positive `tabindex`; use DOM order. `tabindex="-1"` only for programmatic focus targets.
- After navigation or content replacement, move focus to the new heading or container (`el.focus()`), so screen reader and keyboard users are not left behind.
- Sticky headers: `scroll-padding-top` so focused items are not hidden (2.4.11).

## Dialogs and popovers

```html
<dialog id="d" aria-labelledby="d-title">
  <h2 id="d-title">Delete project?</h2>
  <button type="button" id="cancel">Cancel</button>
  <button type="button" id="ok">Delete</button>
</dialog>
```
```js
dialog.showModal();          // native: traps focus, inert background, Esc closes
trigger.focus();             // on close, return focus to the opener (the dialog 'close' event)
```
Custom dialogs: `role="dialog" aria-modal="true"` + label, focus moved inside on open, focus trap, Esc closes, background `inert`, focus returns on close.

## Status messages and live updates

```html
<div role="status" aria-live="polite" id="toast"></div>      <!-- polite updates: saved, 3 results found -->
<div role="alert" id="error"></div>                          <!-- urgent: errors -->
```
Insert text into an existing live region (it must exist before the update). Do not move focus for non-critical messages; do not make toasts the only place for essential information or auto-dismiss too fast.

## Tabs, menus, accordions (follow the ARIA Authoring Practices)

- Accordion: `<button aria-expanded="true|false" aria-controls="panel">`; the panel is the region. Native `<details><summary>` often suffices.
- Tabs: `role=tablist/tab/tabpanel`, `aria-selected`, roving `tabindex` (arrow keys move, Tab leaves the list), Home/End.
- Menus: avoid `role="menu"` for site navigation (use a list of links in a `<nav>` with a disclosure button); true application menus need full arrow-key behavior.
- Combobox, listbox, tree, grid: follow the APG patterns exactly or use a tested library (Radix, React Aria, Headless UI, Reach).

## Tables

```html
<table>
  <caption>Quarterly revenue</caption>
  <thead><tr><th scope="col">Quarter</th><th scope="col">Revenue</th></tr></thead>
  <tbody><tr><th scope="row">Q1</th><td>$10M</td></tr></tbody>
</table>
```
Do not use tables for layout. On small screens keep the table markup (scroll the container or reflow with CSS), not div soup.

## Color and contrast

- Text 4.5:1 (large text 3:1); UI parts, icons and focus rings 3:1; check hover, focus, disabled (disabled is exempt but should remain legible), placeholder, text on images/gradients.
- Never use color alone: add text, icon, pattern or underline (links in text must be distinguishable by more than color).
- Verify with `ui_audit.py --pair <fg> <bg>`; adjust token values in one place (see `design-ui-ux` visual system).

## Motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; scroll-behavior: auto !important; }
}
```
Provide pause/stop for carousels and auto-updating content; no autoplay with sound; nothing flashing more than three times per second.

## Zoom, reflow and spacing

- Use relative units (rem, %, ch), no fixed heights on text containers, `max-width` with `min()`; flex/grid that wraps; test at 320 px.
- Never `user-scalable=no` or `maximum-scale=1`. Let users override line height and spacing without clipping.

## Media

Captions for video, a transcript for audio, no autoplay with sound, visible and keyboard-operable controls, audio description or an alternative for important visual-only content.

## Touch targets

At least 24x24 CSS px (WCAG 2.2 minimum), ideally 44x44; give small icon buttons padding (not just a bigger icon); keep spacing between adjacent targets.

## ARIA rules of thumb

1. Do not use ARIA if a native element does the job.
2. Do not change native semantics (`<h2 role="button">`).
3. Every interactive ARIA control must work with the keyboard.
4. Do not use `role="presentation"` or `aria-hidden="true"` on focusable elements.
5. Every interactive element has an accessible name.

## Retest checklist after fixing

Run `a11y_audit.py` again; tab through the flow; zoom to 200% and 320 px; use a screen reader on the changed part; verify no visual regression; add a lint rule or automated test (eslint-plugin-jsx-a11y, jest-axe, Playwright with axe) to keep it fixed.
