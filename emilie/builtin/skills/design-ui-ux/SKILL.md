---
name: design-ui-ux
phase: rencana
description: Design the user experience and interface of a screen, flow or product - users and tasks first, the shortest flow, every screen state (empty, loading, error, success, partial), forms, copy, a small token-based visual system, responsive and accessibility rules, and a spec that a developer can build. Includes an audit script for CSS contrast and basic HTML accessibility. Also covers terminal and CLI interfaces. Not for implementation (build-feature) or a full WCAG review (accessibility-check). Triggers - "design the UI", "UX", "wireframe", "user flow", "layout for", "design system", "color palette", "form design", "landing page", "improve this screen", "mockup".
---

# Design UI/UX

**Goal:** an interface where a real person can finish their task quickly, without confusion, on the devices and with the
abilities they actually have, specified clearly enough that a developer builds it without guessing.

## Ground rules

1. **Users and tasks first.** Name who uses it, what they want to get done, in what situation (device, attention, mood,
   expertise), and what "done" looks like. Design the task flow before the look.
2. **Fewest steps, fewest decisions.** Remove, merge or default every step you can. Each field, choice and screen must earn
   its place.
3. **Design all the states, not only the happy one.** Every screen has: empty, loading, partial, error, success, no-permission,
   offline or slow, and too-much-data. Unspecified states get built badly.
4. **Read before you design.** In an existing product, read the current components, tokens and copy (Step 2) and reuse them.
   A new pattern needs a reason. Consistency beats local cleverness.
5. **Content is design.** Real words and real data in the layout, not "Lorem ipsum" and "User 1". Labels say what happens
   (`Save changes`, not `Submit`).
6. **Accessibility is a requirement, not a polish step.** Keyboard operation, visible focus, contrast, labels, text
   resizing, no color-only meaning, and touch targets of at least 44 px are specified up front.
7. **A system, not one-offs.** Colors, type sizes, spacing, radii and shadows come from a small set of tokens. Components are
   reused and have defined states.
8. **Evidence over taste.** Back decisions with the task, a known heuristic, existing user data, or a quick test with
   a real person. Say when something is an opinion.
9. **Match the platform.** Web, mobile, desktop and terminal each have conventions; follow them unless there is a reason.
10. **Mark each fact** as **Given**, **Checked** (seen in the code or product), **Assumed** or **Unknown**. This skill specifies;
    it does not edit the code unless asked to implement.
    If a script could not be run (needs approval, missing runtime, no network), say "not run" and why; never describe a plan, schema or contract as validated or linted unless the tool actually ran.

## Procedure

### Step 1 - Understand the user and the job

Write short answers: who, what job (in the form "when ___, I want to ___, so I can ___"), where and on what device, how often,
what they know already, what goes wrong today, and the success measure (time to finish, errors, conversion). List the
constraints: brand, platform, existing design system, languages, accessibility target (default WCAG 2.1 AA), performance.
Ask the user once about the gaps that matter; otherwise state assumptions. If requirements are unclear, load `clarify-requirements`.

### Step 2 - Learn what exists

Skip for a new product. Otherwise find the styles and components (CSS or design tokens, component folders, a Storybook or
style guide) and run:

```
python "<this skill's directory>/scripts/ui_audit.py" <css-or-html-file-or-folder>
python "<this skill's directory>/scripts/ui_audit.py" --pair <foreground> <background> [--large]
```

The audit checks text contrast per CSS rule (including `var(--token)` values and the dark scheme), removed focus outlines,
tiny or fixed-pixel text, and in `.html` files: language, title, viewport and zoom, image alt text, form labels, nameless
buttons and links, heading order, clickable `div`s, positive `tabindex`, duplicate ids. `--pair` computes a contrast
ratio and suggests the nearest passing color. It reads static files only; templates in JSX or Vue must be read by hand or
rendered first. Record the existing tokens, components and writing style you will reuse.

### Step 3 - Map the task flow

Draw the shortest path from the user's goal to done as numbered steps (text is fine): entry point, each screen or decision, the
data needed at each step, exits and recovery, where the user can go back, and what is saved if they leave. Check it against the
alternatives: fewer screens, defaults, progressive disclosure, doing it inline instead of a new page. Include the first-time and
the returning-user paths and the unhappy ones (validation fails, network drops, session expires, user cancels).

### Step 4 - Lay out each screen

For each screen: its single primary action, the information hierarchy (what is read first, second, third), the layout in a
text wireframe (`references/screen-spec-template.md`) at the smallest and the largest supported width, and the components
used. One primary action per view; secondary actions are visually quieter; destructive actions are separated, named plainly and
confirmed or made undoable (undo beats "Are you sure?").

### Step 5 - Specify every state and interaction

Fill the state table for each screen: **empty** (say what to do next), **loading** (skeletons or a progress bar after about
a second, never a blank page), **success** (confirm what changed), **error** (what happened, why if known, how to fix, keep
the user's input), **partial** and **offline**. Specify keyboard behavior (tab order, shortcuts, Escape closes), focus handling
when content changes or dialogs open, hover/focus/active/disabled states, and animations (short, purposeful, respect
`prefers-reduced-motion`). Forms follow `references/ux-principles.md`: visible labels, the right input type, inline validation
after the user leaves a field, clear error text, preserve input, mark optional rather than required, one column.

### Step 6 - Define the visual system

Use `references/visual-system.md`: a small token set (color roles for text, surface, border, accent, status, in light and dark
if needed; a type scale; a spacing scale on a 4 or 8 px grid; radii; shadows; breakpoints). Check every text-on-surface pair
with `ui_audit.py --pair` and write the ratios down. Reuse the project's tokens when they exist; extend them rather than
adding parallel ones. Color never carries meaning alone (add an icon or text).

### Step 7 - Write the copy

Write the real strings: titles, labels, buttons, helper text, empty states, errors, confirmations, in the product's voice
and (if relevant) ready for translation (no sentences built from fragments, room for 40% longer text). Errors say what to do,
not just what went wrong.

### Step 8 - Review and deliver

Run the checklist in `references/ux-principles.md` (heuristics and accessibility). Walk the main task as a first-time user
using only the spec. If the project has HTML or CSS, run `ui_audit.py` on it and fix or explain each warning. Deliver the spec
using `references/screen-spec-template.md`; if the user wants a visual, offer an HTML prototype or an artifact. Suggest a
5-person usability test of the main task as the next validation step. Offer `build-feature`, `accessibility-check`, and
`break-down-tasks` as hand-offs.

## Definition of done

- [ ] The user, job, context and success measure are written down.
- [ ] The flow is the shortest reasonable one, with unhappy paths and recovery included.
- [ ] Each screen has one primary action, a hierarchy, and a wireframe for small and large widths.
- [ ] Every screen lists its empty, loading, error, success and offline states, plus keyboard and focus behavior.
- [ ] Tokens (color roles, type, spacing) are defined or reused, and each text pair's contrast is recorded and passes AA.
- [ ] Copy is written with real strings, including errors and empty states.
- [ ] Touch targets are at least 44 px, focus is visible, nothing relies on color alone.
- [ ] `ui_audit.py` ran on any existing HTML/CSS involved, and every warning is fixed or explained.

## Pitfalls

- **Designing the screen before the task.** Pretty layouts that bury the primary action.
- **Happy-path-only specs.** The empty list and the failed save are where users get lost.
- **Placeholder as label.** It disappears while typing and has poor contrast. Use a visible label.
- **Low-contrast "elegant" gray text**, tiny type, and tap targets under 44 px.
- **Color-only status** (red/green dots) with nothing for color-blind users or screen readers.
- **Modal overload and "Are you sure?" on everything.** Prefer undo; reserve confirmation for the irreversible.
- **Disabled buttons with no explanation.** Show what is missing instead.
- **Custom controls replacing native ones** (select, checkbox, date) without matching their keyboard and screen-reader behavior.
- **Infinite choices.** More than a handful of options, settings or nav items at one level hide the important one.
- **Fixed-pixel layouts and text.** Use relative units; test at 200% zoom and narrow widths.
- **Copying a trend.** Check it against your users' task and devices.
- **Skipping the test.** Five people trying the task finds most problems.

## Hand-offs

| Next | Load |
|---|---|
| unclear requirements | `clarify-requirements` |
| data or API behind the screens | `design-api`, `design-database` |
| structure of the front end | `design-architecture` |
| build it | `build-feature` |
| full accessibility review | `accessibility-check` |
| task breakdown | `break-down-tasks` |
| slow screens | `profile-performance` |
