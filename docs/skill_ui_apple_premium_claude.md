# Skill — Apple‑Grade Minimal Premium UI (Dark Mode Default) — Claude

**Purpose:** Generate UI/UX specs (and optionally UI code) that feel polished, minimalist, and premium — “it just works.”

**Default:** Dark mode is the baseline. Only produce a light theme if explicitly requested.

---

## 0) Mental model: what “Apple‑grade” means

- **Focus:** Every screen has one primary job and one primary action. Everything else is secondary.
- **Clarity:** Users should never ask “what is this?” or “what happens if I tap this?”
- **Deference to content:** UI recedes; content is the hero.
- **Depth with restraint:** Use layers, elevation, and motion sparingly to communicate hierarchy, not to decorate.
- **Detail:** Typography, spacing, alignment, states, and microcopy are as important as layout.
- **Integrated experience:** Flows, data states, and error handling are designed end‑to‑end.

---

## 1) Inputs you should assume (unless provided)

If the user does not specify, assume:

- Platform: **web app** (responsive), touch + mouse + keyboard.
- Audience: general.
- Tone: confident, calm, neutral.
- Theme: **dark default**.
- Accessibility target: **WCAG AA**.

If the user *did* specify platform (iOS/macOS/Android/desktop), prioritize native patterns for that platform.

---

## 2) Operating protocol (agentic workflow)

### Step A — Clarify the “job” (minimal questions)
If context is missing, ask **at most 2** high‑impact questions:
1) Who is the user + top task?  
2) What is the primary screen/flow output (list, dashboard, editor, checkout, etc.)?

If the user already gave enough, **don’t ask** — proceed.

### Step B — Define the information architecture (IA)
- Write 3–7 bullets:
  - Primary user goal
  - Primary action
  - Key objects (what things exist: projects, invoices, messages…)
  - Key screens (max 5–7 for first pass)

### Step C — Compose the layout (content-first)
- Establish hierarchy: title → key metric/content → primary action → secondary actions.
- Reduce cognitive load: chunk content into 1–3 sections max per screen.
- Use progressive disclosure: hide advanced/rare controls behind “More”.

### Step D — Define the component inventory + states
For each component, specify:
- Purpose
- Variants (primary/secondary/tertiary)
- States (default/hover/focus/active/disabled/loading/error/success)
- Empty state + error state copy

### Step E — Define design tokens (dark-first)
Provide tokens for:
- Color (bg/surface/border/text/accent/semantic)
- Typography (font stack, sizes, weights, line height)
- Spacing scale (8pt grid)
- Radius and elevation
- Motion (durations + easing)
- Focus ring style

### Step F — Accessibility & ergonomics pass
- Tap targets: >= 44×44pt equivalent.
- Contrast: WCAG AA for text; focus visible.
- Keyboard navigation: logical tab order; escape closes modals.
- Reduced motion support.

### Step G — “Just works” reliability pass
- Every screen must specify: **loading, empty, error, offline/slow**, and **success**.
- Prefer undo/rollback to irreversible actions.
- Validate inputs early; preserve user data on failures.

---

## 3) Visual style rules (dark, minimalist, premium)

### 3.1 Color (dark-first)
- Background: near-black (avoid pure #000 unless necessary for OLED).
- Surfaces: slightly lighter than background to create hierarchy (2–3 surface levels max).
- Borders: hairline, low-contrast.
- **One accent color** (use sparingly; reserve for primary action + key highlights).
- Use semantic colors for status (success/warn/error) but keep saturation controlled.
- Never rely on color alone to convey meaning.

### 3.2 Typography
- Use system UI font stack.
- Prefer fewer sizes; aim for:
  - Title, Section title, Body, Caption (4 tiers).
- Use weight to communicate hierarchy (not color).
- Maintain comfortable line length and line height.

### 3.3 Spacing + layout
- 8pt spacing system.
- Prefer generous padding and strong alignment.
- Avoid dense “data-wall” layouts unless explicitly requested.
- Keep a single dominant column; use a secondary column only when needed.

### 3.4 Materials, elevation, and borders
- Use elevation sparingly: 0–2 levels for cards; 1 level for modals/popovers.
- Avoid heavy shadows; prefer subtle shadow + border in dark mode.
- Corners: consistent radius across components (e.g., 12 for cards, 10 for buttons, 8 for inputs).

### 3.5 Motion
- Motion communicates cause/effect and hierarchy.
- Use short, natural transitions (≈150–250ms).
- Avoid bouncy/novelty animations; respect reduced-motion.

---

## 4) UX behavior rules (the “it just works” checklist)

- **One primary action per screen.** Secondary actions are visually quieter.
- **No surprises:** predictable placement, consistent labels, and consistent component behavior.
- **Immediate feedback:** on click/tap, show pressed state instantly; show loading within 150ms if needed.
- **Undo over confirm:** where possible, allow reversal instead of “Are you sure?”.
- **Error prevention:** constrain inputs, provide defaults, and validate inline.
- **Helpful empty states:** explain what’s empty and provide a next step.
- **Search and filtering:** if lists exceed ~20–30 items, include search; filters are secondary.
- **Forms:** label fields clearly; avoid placeholder-only labels; show requirements and examples.

---

## 5) Default token set (starter)

Use this as a baseline and adapt to the product:

### Color tokens (example)
- `bg/0`: #0B0B0C  
- `surface/1`: #121214  
- `surface/2`: #1A1A1F  
- `border/1`: #2A2A33  
- `text/primary`: #F5F5F7  
- `text/secondary`: #A1A1AA  
- `accent`: #0A84FF  
- `danger`: #FF453A  
- `warning`: #FF9F0A  
- `success`: #32D74B

### Type scale (example)
- Title: 24/30, weight 600  
- Section: 16/22, weight 600  
- Body: 14/20, weight 400–500  
- Caption: 12/16, weight 400

### Spacing (8pt grid)
`4, 8, 12, 16, 24, 32, 40, 56, 72`

### Radius
- Input: 10
- Button: 10
- Card: 12
- Modal: 16

### Motion
- Fast: 120ms
- Standard: 180ms
- Slow: 240ms
Easing: ease-out for entrance, ease-in for exit

---

## 6) Output format (what you should produce)

### If user asks for design/spec only
Return:

1) **UI summary** (1–3 sentences)  
2) **IA & primary action** (bullets)  
3) **Wireframe description** (section-by-section)  
4) **Tokens** (colors/type/spacing/radius/elevation/motion)  
5) **Component inventory** (variants + states)  
6) **Empty/error/loading/offline** behaviors + microcopy  
7) **Accessibility notes**  
8) **QA checklist**

### If user asks for implementation
Provide the above **plus** code in their stack. If they didn’t specify a stack, ask 1 question (“React/Tailwind, SwiftUI, Flutter, or something else?”). If they say “any”, default to **React + CSS variables**.

---

## 7) Quality bar (self-review before final)

- Does the screen have a single clear primary action?
- Is the hierarchy obvious in 3 seconds?
- Are states fully defined (loading/empty/error/offline/disabled)?
- Is the UI consistent and minimal (no extra boxes, no visual noise)?
- Does it meet accessibility basics (contrast, focus, targets)?
- Does it feel calm, predictable, and “inevitable”?
