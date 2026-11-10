# Visual system: tokens and rules

Define a small set of named tokens once and use them everywhere. If the project already has tokens, reuse and extend them.
Check every text and surface pair with `scripts/ui_audit.py --pair <fg> <bg>` and record the ratio.

## Color roles (name by role, not by hue)

| Token | Role | Notes |
|---|---|---|
| `--bg` | page background | |
| `--surface` | cards, panels | slightly different from bg |
| `--text` | primary text | 7:1 or more on `--bg` ideally |
| `--text-muted` | secondary text | still 4.5:1 on its surface |
| `--border` | dividers, outlines | 3:1 against the surface when it marks a control edge |
| `--accent` | primary action, links, focus | 4.5:1 as text, 3:1 as a button edge |
| `--accent-contrast` | text on `--accent` | 4.5:1 on the accent |
| `--danger`, `--warning`, `--success`, `--info` | status | always paired with an icon or text |
| `--focus` | focus ring | 3:1 against both neighbors |

Rules: one accent plus neutrals covers most products. Limit saturated colors; use status colors only for status. Define a
dark theme by redefining the same tokens (not new ones) under `prefers-color-scheme: dark` (and a manual toggle if offered); don't
invert images or use pure black on pure white. Check contrast in both themes.

```css
:root { --bg:#ffffff; --surface:#f6f7f9; --text:#14181f; --text-muted:#4b5563; --accent:#0b5bd3; --accent-contrast:#ffffff; --focus:#0b5bd3; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --bg:#0f1115; --surface:#181b22; --text:#eceff4; --text-muted:#a6adbb; --accent:#6ea8ff; --accent-contrast:#0f1115; --focus:#6ea8ff; }
}
```

## Typography

- One or two families (a system font stack is a fine, fast default). Body at 16 px (1rem) or larger, line-height 1.4 to 1.6, line length 45 to 75 characters.
- Modular scale, for example 1.25: 12, 14, 16, 20, 25, 31, 39 px; define as `--text-sm`, `--text-base`, `--text-lg`, `--h3`, `--h2`, `--h1`.
- Use `rem`, not `px`, so user font settings work. No more than 3 or 4 sizes on one screen. Weights: 400 body, 600 emphasis, 700 headings.
- Don't use all-caps for long text; align text left (right for RTL); avoid justified text on the web.

## Spacing and layout

- 4 or 8 px base unit: 4, 8, 12, 16, 24, 32, 48, 64. Use the scale, not arbitrary values.
- Group related items closer than unrelated ones (proximity). Align to a grid; consistent gutters; generous whitespace around the primary action.
- Mobile first: single column from 320 px; breakpoints where the content breaks (about 640, 1024, 1280), not per device.
- Max content width around 1100 to 1200 px for text-heavy pages; don't stretch lines across wide screens.
- Use CSS grid/flex and `min()/clamp()` for fluid sizes; no fixed-height containers for text.

## Shape, depth and motion

- Radii from a short scale (4, 8, 16, full). Borders and a few shadows for elevation (card, popover, modal), not everywhere.
- Motion 120 to 250 ms with ease-out for entrances and ease-in for exits; animate opacity and transform only; stop or reduce under
  `@media (prefers-reduced-motion: reduce)`. Never animate for decoration on repeated actions.

## Components (define each with states)

Button (primary, secondary, ghost, destructive; default, hover, focus-visible, active, disabled, loading), link, text input
(default, focus, filled, error, disabled, read-only), select, checkbox, radio, switch, tabs, modal/dialog, toast, tooltip, card,
table, list item, pagination, empty state, skeleton, avatar, badge. For each: anatomy, sizes, states, keyboard behavior,
ARIA pattern, and where it must not be used.

- Buttons: min height 44 px on touch; padding from the spacing scale; label 14 to 16 px; loading keeps width and blocks double clicks.
- Focus: `:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }`. Never remove outlines without a replacement.
- Icons: pair with text when meaning is not universal; give icon-only buttons an `aria-label` and a tooltip.
- Tables: real `<table>` markup with header cells; on narrow screens reflow to cards or allow scroll within the container only.
- Toasts: don't carry critical information or require action; announce with `role="status"`.
- Dialogs: focus moves in, is trapped, Escape closes, focus returns to the trigger; page behind is inert.

## Responsive and internationalization

- Test at 320, 768, 1280 px, at 200% zoom, and with long words and translations (German, Finnish) and RTL if relevant.
- Use logical properties (`margin-inline`, `padding-block`) so RTL works. No text in images. Dates, numbers and currency use locale formatting.

## Images and media

- Provide width and height (or aspect-ratio) to prevent layout shift; responsive `srcset`; modern formats; lazy-load below the fold.
- Meaningful images get alt text that states the purpose; decorative images get `alt=""`. Captions or transcripts for video and audio; no autoplay with sound.

## Performance targets for UI

Largest Contentful Paint under 2.5 s, Interaction to Next Paint under 200 ms, Cumulative Layout Shift under 0.1 on a mid-range phone
over a typical mobile connection. Budget images, fonts (subset, `font-display: swap`), and JavaScript; measure rather than guess
(see `profile-performance`).
