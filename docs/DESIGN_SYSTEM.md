# Design System — Liquid Glass

The interface should feel like a native macOS application, not a web page. That
target drives every decision below. The whole system lives in
`frontend/src/styles/index.css`; components compose tokens and never hard-code
a colour.

## What makes glass read as a material

Translucency alone looks like a low-opacity `div`. Four properties together
make a surface read as a physical pane:

| Property | Implementation | Why it matters |
|---|---|---|
| Tint | `--glass-tint` | the body of the material |
| Blur **with saturation** | `blur(24px) saturate(180%)` | re-saturates colour bleeding through; this is the difference between macOS vibrancy and a grey smear |
| Specular highlight | a 1px gradient on `::after`, top edge | light catching the bevel — the single biggest contributor |
| Shadow | `--glass-shadow` | separates the pane from what is behind it |

Remove any one and the effect collapses. The saturation boost and the top-edge
highlight are the two most often omitted, and the two that matter most.

**Glass needs something to refract.** `body::before` paints three fixed radial
gradients — blue, violet, green, matching the three learning tracks. Without
that wash, a blurred panel over a flat background is indistinguishable from an
opaque one.

## Materials

```
.glass          blur 24px, saturate 180%   cards, panels — the default
.glass-strong   blur 40px, saturate 200%   modals, sheets, auth card
.glass-thin     blur 12px, saturate 160%   sidebars, toolbars
.glass-inset    inset shadow, no blur      input fields — light falls *into* the surface
.glass-interactive  hover lift, press scale
```

Exposed through `<GlassPanel material="strong" radius="2xl">`.

## Tokens

### Colour — OKLCH throughout

Every colour is `oklch()`. Unlike HSL, OKLCH is perceptually uniform: two
colours with the same lightness *look* equally light regardless of hue. That
property is what lets the three track colours sit side by side without one
appearing to jump forward, and it makes generating the accent ramp a matter of
varying one number.

```
--color-accent-*            macOS system blue, 50–900
--color-track-foundation    cyan-blue
--color-track-intermediate  green
--color-track-advanced      violet
--color-success / warning / danger / info
```

### Semantic variables

Theme-dependent values are indirected through semantic names, redefined under
`.dark`:

```
--surface-canvas / --surface-raised / --surface-sunken
--text-primary / --text-secondary / --text-tertiary
--glass-tint / --glass-border / --glass-highlight / --glass-shadow
--hairline · --focus-ring
```

Dark mode is not an inversion. Dark glass needs a *brighter* highlight
(`oklch(1 0 0 / 0.16)` vs `0.9`) and a much deeper shadow to read as
translucent — which is why every material property is its own variable rather
than a computed inverse.

### Typography

```
--font-sans: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Inter', …
```

The system stack renders **SF Pro on Apple platforms** — the single biggest
contributor to feeling native — and degrades gracefully elsewhere without
shipping a web font.

Tracking tightens as text grows, matching macOS optical sizing:
`--tracking-display` (-0.028em) → `--tracking-title` → `--tracking-body`.

### Radii and motion

Radii run 6 → 32px (`--radius-xs` … `--radius-2xl`).

```
--ease-spring     cubic-bezier(0.34, 1.56, 0.64, 1)   gentle overshoot
--ease-out-soft   cubic-bezier(0.22, 1, 0.36, 1)      entrances
--duration-fast/base/slow   140 / 240 / 420ms
```

The slight overshoot is what reads as "native". Linear or plain ease-out reads
as "web page".

## Components

| Component | Purpose |
|---|---|
| `GlassPanel` | the base surface — material × radius × interactive |
| `Button` | 5 variants × 3 sizes; disabled and `aria-busy` while loading |
| `Input` | labelled field with `aria-invalid` / `aria-describedby` wiring |
| `ThemeToggle` | segmented control, implemented as a `radiogroup` |
| `Spinner` / `FullPageSpinner` | `role="status"` with an accessible label |
| `Logo` / `Wordmark` | inline SVG, inherits `currentColor` |
| `ErrorBoundary` | catches render errors; themed fallback |

## Theming

Driven by a `.dark` class on `<html>`, **not** `prefers-color-scheme` alone, so
an explicit user choice can override the OS. Choosing *System* attaches a live
`matchMedia` listener, so the app follows macOS switching to dark at sunset
without a reload.

An inline script in `index.html` applies the stored theme **before first
paint**. It must be synchronous and inline — anything deferred runs after the
browser has painted a light-theme body, producing a white flash on every load
for dark-mode users.

## Accessibility

- `prefers-reduced-motion` collapses every animation; the motion here is
  decorative by design.
- `:focus-visible` shows a 2px accent ring at a 2px offset on every interactive
  element.
- Errors use `role="alert"` and are referenced by `aria-describedby`; a visual
  red border alone is invisible to a screen reader and to most colour-blind
  users.
- Loading buttons set `aria-busy` — the spinner is invisible to assistive tech.
- The theme control is a `radiogroup`, so arrow keys work and the selection is
  announced.
- `@supports not (backdrop-filter)` falls back to an opaque surface, so older
  browsers get readable text rather than a transparent mess.

## Conventions

Reference CSS variables as `bg-[var(--surface-raised)]`. Tailwind v4 dropped
the bare `[--var]` shorthand; the explicit `var()` form is valid everywhere.

Compose classes with `cn()` (`clsx` + `tailwind-merge`) so a caller's `px-6`
reliably overrides a component's default `px-4` instead of both landing in the
class list where the winner depends on stylesheet order.
