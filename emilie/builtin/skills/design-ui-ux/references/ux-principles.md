# UX principles and review checklist

## Heuristic review (Nielsen's 10, applied)

1. **Visibility of status.** The user always knows what is happening: progress, saved/unsaved, where they are.
2. **Match the real world.** Words and order the user uses, not internal names (`Invoices`, not `Billing entities`).
3. **User control and freedom.** Undo, cancel, back; an emergency exit from any state; drafts survive.
4. **Consistency and standards.** Same word, same place, same behavior; follow platform conventions.
5. **Error prevention.** Constraints, sensible defaults, confirmation only for the irreversible; disable with an explanation.
6. **Recognition over recall.** Show options and recent items; do not make users remember across screens.
7. **Flexibility and efficiency.** Shortcuts, bulk actions, saved filters for experts, without hiding basics from novices.
8. **Minimalist design.** Every extra element competes with the important one. Remove, then remove more.
9. **Help recover from errors.** Plain words, the cause, the fix, and keep the input.
10. **Help and documentation.** Short, searchable, in context; the interface should need little of it.

## Flows

- Start from the goal; count steps and decisions; try to halve them (defaults, pre-filled data, remembered choices, inline editing).
- Progressive disclosure: show the common 80% first; put the rest under "More options".
- One primary action per view. Make the next step obvious after success.
- Don't force an account before value unless essential; ask for information at the moment it is needed.
- Onboarding teaches by doing, is skippable, and is not the only place a feature is explained.
- Long processes: show steps and progress, allow save and resume, let people go back without losing data.
- Destructive actions: name the object ("Delete project Apollo"), state the consequence, prefer undo (soft delete for a time).

## Screen states (specify all)

| State | Requirements |
|---|---|
| Empty (first use) | Explain the value, one clear action to start, example or template |
| Empty (no results) | Say so, show the active filters, offer to clear them or broaden the search |
| Loading | Skeleton or spinner after ~1 s; layout does not jump; long waits show progress and can be cancelled |
| Partial | Show what loaded; mark what failed with retry for just that part |
| Error | What happened, why (if known), what to do, retry; keep the user's input; no blame, no codes only |
| Success | Confirm what changed and where to see it; offer the next step; undo when possible |
| Disabled / no permission | Say why and who can do it |
| Offline / slow | Queue the action or say it cannot be done now; show last known data with its age |
| Too much data | Pagination or virtual lists, search, filters, sensible limits |

## Forms

- One column. Visible label above the field; helper text for format and why you ask.
- Right input types (`email`, `tel`, `number`, `date`) and `autocomplete` attributes; mobile keyboards match.
- Mark **optional** fields (most fields should be required, or gone). Ask only what you need.
- Validate after the user leaves the field (and on submit); never block typing. Show the error next to the field and in a
  summary at the top for long forms; move focus to the first error.
- Error text: what to change ("Enter a date like 2026-03-04"), not "Invalid input".
- Keep what the user typed on errors and reloads. Do not clear forms.
- Buttons: a specific verb ("Create account"); primary on the side the flow continues; show a busy state and prevent double submit.
- Passwords: allow paste and a show toggle; explain rules before the error, not after.
- Dates, addresses, phone numbers: accept common formats; format for them.

## Writing (microcopy)

- Plain words, short sentences, active voice, same term for the same thing everywhere.
- Buttons say what happens (`Save changes`, `Send invite`, `Delete project`). Avoid `OK`, `Submit`, `Yes/No` for important actions.
- Empty state: what this is, why it is empty, what to do.
- Error: what happened + how to fix. Never "Something went wrong" alone.
- Do not build sentences by joining fragments; plan for translation (longer text, different word order, plurals, dates).
- Tone matches the moment: calm and clear in errors; no jokes when users lose data.

## Accessibility baseline (design-time checklist)

- Everything works with the keyboard alone; focus order matches visual order; focus is always visible (2 px outline, 3:1 against neighbors).
- Contrast: text 4.5:1 (3:1 for large text 24 px, or 18.66 px bold); UI boundaries, icons and focus rings 3:1.
- Information is not conveyed by color alone; links are distinguishable beyond color.
- Targets at least 44x44 px (24x24 px is the WCAG 2.2 AA minimum) with spacing.
- Every control has a programmatic name; images have alt text or are marked decorative; headings form an outline; landmarks exist.
- Text can be resized to 200% and reflows at 320 px width without horizontal scrolling.
- Motion is optional (`prefers-reduced-motion`), nothing flashes more than 3 times per second, no autoplay with sound.
- Time limits can be extended; errors are announced to assistive technology; dialogs trap and return focus.
- Don't disable zoom. Don't rely on hover alone.

## Terminal and CLI interfaces

- Make the common case a short command; `--help` with examples; sensible defaults; consistent flag names.
- Output for humans by default (aligned, concise), machine output behind `--json`; stable exit codes (0 success, non-zero failure).
- Respect `NO_COLOR` and non-TTY output; never use color alone; keep line widths reasonable.
- Progress for anything over about a second; destructive actions ask for confirmation or support `--dry-run` and `--yes`.
- Errors go to stderr with the fix; no stack traces unless `--verbose`.
- TUIs: show key hints, support Esc/q to leave, never trap the user, keep working in small terminals (80x24), and avoid reliance on a mouse.

## Quick usability test (5 people)

1. Pick the 3 most important tasks. Write them as goals, not instructions ("Find out when your order arrives").
2. Ask each person to do them aloud, without help. Observe; do not explain.
3. Note where they hesitate, mis-click, or give up; count task completion and time.
4. Fix the issues that blocked several people first; retest. Five people reveal most major problems.
