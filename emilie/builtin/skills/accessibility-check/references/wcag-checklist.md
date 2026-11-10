# WCAG 2.2 AA checklist and test procedures

Organized by the four principles (POUR). "How to test" gives the quickest reliable check. Level A items are also required at AA.

## 1. Perceivable

| SC | Requirement | How to test |
|---|---|---|
| 1.1.1 Non-text content (A) | Images, icons and controls have text alternatives; decorative images are hidden (`alt=""`) | scan for missing alt; read each alt: does it give the purpose/content? Charts need a text summary or data table |
| 1.2.1 to 1.2.5 Time-based media (A/AA) | Captions for prerecorded and live audio, transcripts or audio description for video | check `<track>`, caption quality, transcript link |
| 1.3.1 Info and relationships (A) | Structure is in the markup: headings, lists, tables with headers, form labels, landmarks | disable CSS (or use a screen reader's heading/landmark lists); structure must still make sense |
| 1.3.2 Meaningful sequence (A) | DOM order matches reading order | tab and read in order; compare with the visual layout |
| 1.3.3 Sensory characteristics (A) | Instructions do not depend only on shape, color, position or sound ("the red button on the right") | read the instructions |
| 1.3.4 Orientation (AA) | Works in portrait and landscape | rotate the device/viewport |
| 1.3.5 Identify input purpose (AA) | Personal-data fields use `autocomplete` | scan; check name, email, tel, address, password |
| 1.4.1 Use of color (A) | Color is not the only way to show information, errors or links | grayscale view; links need underline or another cue |
| 1.4.2 Audio control (A) | Audio over 3 s can be paused/stopped | autoplay check |
| 1.4.3 Contrast (AA) | Text 4.5:1 (large 3:1) | scanner; `ui_audit.py --pair`; check states and images behind text |
| 1.4.4 Resize text (AA) | 200% zoom without loss of content/function | browser zoom 200% |
| 1.4.5 Images of text (AA) | Use real text, not pictures of text | inspect logos excepted |
| 1.4.10 Reflow (AA) | At 320 CSS px width (400% zoom) no two-dimensional scrolling | narrow the window to 320 px |
| 1.4.11 Non-text contrast (AA) | UI component boundaries, icons, focus indicators, chart parts 3:1 | check borders of inputs, icons, focus ring |
| 1.4.12 Text spacing (AA) | Content survives user text spacing (line height 1.5, paragraph 2x, letter 0.12em, word 0.16em) | apply a text-spacing bookmarklet or CSS override |
| 1.4.13 Content on hover or focus (AA) | Tooltips/popovers are dismissible (Esc), hoverable and persistent | hover and focus each trigger |

## 2. Operable

| SC | Requirement | How to test |
|---|---|---|
| 2.1.1 Keyboard (A) | All functionality via keyboard | unplug the mouse; complete the journeys |
| 2.1.2 No keyboard trap (A) | Focus can always leave a component | tab through everything; check modals, editors, widgets |
| 2.1.4 Character key shortcuts (A) | Single-key shortcuts can be turned off or remapped | list shortcuts |
| 2.2.1 Timing adjustable (A) | Time limits can be turned off, adjusted or extended | session timeouts, carousels |
| 2.2.2 Pause, stop, hide (A) | Moving/auto-updating content over 5 s can be paused | carousels, tickers, animations |
| 2.3.1 Three flashes (A) | Nothing flashes more than 3 times per second | inspect animations/videos |
| 2.4.1 Bypass blocks (A) | Skip link or landmarks to jump the repeated header/nav | first Tab should offer "Skip to content" |
| 2.4.2 Page titled (A) | Each page has a descriptive `<title>` | check titles, including SPA route changes |
| 2.4.3 Focus order (A) | Tab order follows meaning and operation | tab through; look for jumps |
| 2.4.4 Link purpose (A) | Link text makes sense (alone or in context) | list links in a screen reader |
| 2.4.5 Multiple ways (AA) | More than one way to find pages (nav, search, sitemap) | inspect |
| 2.4.6 Headings and labels (AA) | Headings and labels describe their topic/purpose | read the outline |
| 2.4.7 Focus visible (AA) | Keyboard focus is always visible | tab through; ring must be clear |
| 2.4.11 Focus not obscured (AA, 2.2) | The focused element is not hidden behind sticky headers/banners | tab with a sticky header |
| 2.5.1 Pointer gestures (A) | Multi-point/path gestures have single-pointer alternatives | pinch, swipe, drag |
| 2.5.2 Pointer cancellation (A) | Actions fire on release (up-event) and can be aborted | press and drag off |
| 2.5.3 Label in name (A) | Accessible name contains the visible label text | compare visible text and `aria-label` |
| 2.5.4 Motion actuation (A) | Shake/tilt functions have alternatives and can be disabled | device features |
| 2.5.7 Dragging movements (AA, 2.2) | Drag operations have a click/tap alternative | drag-and-drop, sliders |
| 2.5.8 Target size minimum (AA, 2.2) | Targets at least 24x24 CSS px (or enough spacing) | inspect small icons, inline links excepted |

## 3. Understandable

| SC | Requirement | How to test |
|---|---|---|
| 3.1.1 Language of page (A) | `lang` set and valid | scan |
| 3.1.2 Language of parts (AA) | Passages in other languages marked with `lang` | inspect |
| 3.2.1 On focus (A) / 3.2.2 On input (A) | Focus or input does not trigger unexpected context change | tab and change values |
| 3.2.3 Consistent navigation (AA) / 3.2.4 Consistent identification (AA) | Repeated components appear in the same order and with the same names | compare pages |
| 3.2.6 Consistent help (A, 2.2) | Help (contact, chat) is in the same place across pages | compare |
| 3.3.1 Error identification (A) | Errors are identified and described in text | submit invalid forms |
| 3.3.2 Labels or instructions (A) | Visible labels and instructions for inputs | inspect |
| 3.3.3 Error suggestion (AA) | Suggest how to fix errors | read messages |
| 3.3.4 Error prevention (AA) | Legal, financial, data-deleting actions are reversible, checked or confirmed | checkout, delete flows |
| 3.3.7 Redundant entry (A, 2.2) | Do not make users re-enter information already given in the same process | multi-step forms |
| 3.3.8 Accessible authentication (AA, 2.2) | No cognitive test (memorize, transcribe) to log in; paste and password managers allowed | login flows |

## 4. Robust

| SC | Requirement | How to test |
|---|---|---|
| 4.1.2 Name, role, value (A) | Every control exposes name, role and state to AT; custom widgets implement ARIA correctly | screen reader or accessibility tree inspector; scanner for ARIA errors |
| 4.1.3 Status messages (AA) | Status updates are announced without taking focus (`role="status"`, `aria-live`) | trigger toasts, validation, search results with a screen reader |

## Manual test procedures

**Keyboard pass (10 minutes per journey)**: Tab from the top; confirm the first stop is a skip link or the main content entry; every interactive element receives a visible focus ring; Enter/Space activate buttons and links;
arrow keys move within tabs, menus, radio groups; Esc closes dialogs and popovers and returns focus to the trigger; no focus loss when content changes (focus must not drop to `body`); no traps.

**Screen reader pass**: use headings (H), landmarks (D), links lists, and form fields navigation; complete the main task using only the screen reader. Listen for: control names and states ("Save, button", "Menu, collapsed"),
error announcements, live region updates, table headers, and that nothing is read twice or hidden stuff is read. Note the combination (NVDA + Firefox/Chrome, JAWS + Chrome, VoiceOver + Safari, TalkBack + Chrome).

**Zoom and reflow pass**: browser zoom to 200% and 400% (320 px width); check no clipped text, overlapping, hidden controls or sideways scrolling; sticky headers must not cover half the viewport.

**Color pass**: grayscale and a color-blindness simulator; forced-colors/high-contrast mode; dark theme; verify focus rings and icons remain visible.

**Motion pass**: enable "reduce motion" in the OS; parallax, auto-scroll and animations must stop or simplify.

## Severity

| Level | Meaning |
|---|---|
| **Blocker** | Prevents some users from completing a core task at all (no keyboard access, unlabeled required field, inaccessible checkout) |
| **Major** | Serious barrier or very widespread issue with a workaround (low contrast text sitewide, missing error association) |
| **Minor** | Inconvenience or best-practice gap (redundant roles, vague link in a rarely used place) |

## Report template

```
Accessibility audit - <product/pages> - <date>
Standard: WCAG 2.2 AA     Method: automated scan (a11y_audit.py <version>), keyboard, zoom/reflow, screen reader <AT+browser versions>, contrast tools
Scope: <pages, states, devices>      Not tested: <list>

Summary: <n> blockers, <n> major, <n> minor. <Two sentences on the overall picture and the top 3 fixes.>

Findings
[A11Y-001] <title>   Severity: Blocker   WCAG: 2.1.1 Keyboard (A)   Location: <file:line or URL + element>
  Problem: ...    Affected users: ...    Evidence/steps: ...
  Fix: <specific change, code snippet>   Retest: <how>

Passed checks (so effort is not repeated): ...
Recommendations: component-level fixes, design tokens for contrast, tests in CI, accessibility review in design, training.
```
