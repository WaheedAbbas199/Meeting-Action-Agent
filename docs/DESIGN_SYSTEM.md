# Design system and animation utilities

Tokens live in `frontend/css/tokens.css` (colors, spacing, type scale, radii, shadows, motion durations/easings, z-index layers, focus ring). Dark theme overrides the same tokens via `[data-theme="dark"]`; the choice is stored in `localStorage` (`maa.theme`) and nothing else about the user is.

| Layer | File |
|---|---|
| Tokens | `css/tokens.css` |
| Reset/typography/layout helpers | `css/base.css` |
| Motion (keyframes, stagger, reduced-motion) | `css/animations.css` |
| Components (buttons, forms, cards, badges, tables, tabs, modal, drawer, menu, toast, skeleton, empty/error states, stages, timeline, transcript, kanban, charts) | `css/components.css` |
| App shell and auth screens | `css/app.css` |

JS building blocks: `dom.js` (auto-escaping `html` templates, `on` delegation), `ui.js` (toast, modal with focus trap, drawer, confirm dialog, `busy()` button state, badges, states), `chart.js` (accessible SVG bar chart + meter), `icons.js`.

## Motion rules
Transform/opacity only; page enter (fade-up 200ms), dashboard stagger, sidebar collapse, toast/modal/drawer enter/exit, skeleton shimmer, status flash after a server-confirmed change. `prefers-reduced-motion` collapses all animation durations (tested in e2e). Toasts for success appear only after the API call resolves.

## CSP note
Inline `style=""` attributes are blocked by the CSP. Dynamic values travel in `data-*` attributes and are applied through the CSSOM by `hydrate()` in `dom.js`.

## Accessibility
Semantic landmarks, skip link, labelled controls, visible focus rings, `role="dialog"` with focus trap/restore, live regions for toasts and route changes, tables with captions/scopes, chart data tables for screen readers. An axe-core audit (WCAG 2.0/2.1/2.2 A/AA rules) over 16 routes in light and dark themes found 0 violations after fixes. This is automated testing only; it is not a manual screen-reader audit.
