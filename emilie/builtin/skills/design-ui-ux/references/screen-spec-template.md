# UI/UX spec template

Copy, fill in, delete what does not apply. Mark facts: **Given**, **Checked**, **Assumed**, **Unknown**.

---

# <Feature or product> - UX spec

**Status:** draft | proposed | accepted  **Owner:** <name>  **Date:** <YYYY-MM-DD>

## 1. Users and job

| Who | Situation (device, place, attention) | Job: when ___, I want ___, so I can ___ | Success measure |
|---|---|---|---|

Constraints: brand, platform, existing design system, languages, accessibility target (WCAG 2.1 AA), performance budget.

## 2. Task flow

```
1. Entry: <where the user starts>
2. Screen A <name>: <what they do> -> next: B
3. Screen B <name>: decision? yes -> C / no -> A
4. Done: <what they see and can do next>
Unhappy paths: validation fails -> stay on B with errors; network drops -> keep draft, retry; cancel -> confirm only if data would be lost
```

Alternatives considered and why this one is shorter or safer.

## 3. Screens

### Screen: <name>

**Purpose / primary action:** <one sentence>
**Information hierarchy:** 1. ... 2. ... 3. ...

Wireframe, narrow (320-390 px):

```
+--------------------------+
| <  Title                 |
+--------------------------+
| [ Search            ]    |
| Item card                |
|  Title        $12.00     |
|  [ Add to cart ]         |
+--------------------------+
```

Wireframe, wide (>= 1024 px): <sketch or description of the layout change>

Components used: <from the system>
Content/data shown: <real example values>
Interactions: <tap, hover, drag, keyboard shortcuts>

| State | What the user sees | Copy |
|---|---|---|
| Empty (first use) | | |
| Empty (no results) | | |
| Loading | | |
| Success | | |
| Error | | |
| Partial / offline | | |
| No permission | | |

Accessibility: tab order, focus on load and after actions, names of controls, announcements for dynamic changes, reduced motion.

(Repeat per screen.)

## 4. Forms

| Field | Label | Type / autocomplete | Required | Validation and error text | Helper text |
|---|---|---|---|---|---|

Submit button label and busy state; what happens after success and on failure.

## 5. Visual system

Tokens (color roles for light and dark, type scale, spacing scale, radii, shadows, breakpoints), with contrast ratios:

| Text on surface | Foreground | Background | Ratio | Passes (AA) |
|---|---|---|---|---|
| body | #14181f | #ffffff | 17.79:1 | yes |

## 6. Copy deck

| Where | Text |
|---|---|
| Screen A title | |
| Primary button | |
| Empty state | |
| Error: <case> | |
| Confirmation: <case> | |

## 7. Responsive and international

Breakpoints and layout changes, zoom 200%, long text, RTL/locale notes.

## 8. Analytics and validation

Events to measure the success metric; usability test plan (tasks, participants, pass criteria).

## 9. Audit output

Paste the `ui_audit.py` summary for existing HTML/CSS involved and the disposition of every warning.

## 10. Open questions

| # | Question | Owner |
|---|---|---|
