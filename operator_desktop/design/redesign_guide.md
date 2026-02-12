# RemDesk Operator Desktop Redesign Guide (Dark, macOS-inspired)

## Visual direction
- Dark-only UI.
- Glassmorphism used on navigation, toolbar, and cards (not on dense data content).
- Windows-native frame controls remain unchanged.

## Color tokens
Source of truth: `operator/styles.css`.

- `bg_start`: `#090d14`
- `bg_end`: `#0b111b`
- `card`: `rgba(18, 24, 34, 0.58)`
- `card_alt`: `rgba(24, 30, 42, 0.5)`
- `card_strong`: `rgba(18, 24, 34, 0.78)`
- `border`: `rgba(255, 255, 255, 0.14)`
- `border_strong`: `rgba(255, 255, 255, 0.24)`
- `text`: `#eef3ff`
- `muted`: `#9eb0c3`
- `accent`: `#0091ff`
- `accent_2`: `#4db8ff`
- `accent_3`: `#0077d9`
- `good`: `#2dd4bf`
- `warn`: `#f6c970`
- `danger`: `#ff6b6b`

## Layout rules
- Header pattern: `ToolbarCard` with title + subtitle.
- Content pattern: glass cards with consistent spacing and radius.
- Data-heavy sections use splitters/tables with horizontal scroll instead of hidden columns.
- Overflow discoverability: helper hint labels under tables (`TableOverflowHint`).

## Adaptive behavior
- Main client details panel: adaptive `QSplitter`, switches orientation on narrow width.
- Teams page: list/details use `QSplitter`.
- Cookies/Proxy pages: adaptive fixed columns with minimum widths; horizontal scroll when needed.
- Settings page: content is scrollable (`QScrollArea`) to prevent clipping on smaller windows.

## Component states
- Inline status labels use `InlineStatus` + `state` property:
  - `ok`
  - `warn`
  - `error`
- Buttons are standardized by `variant`:
  - `primary`
  - `ghost`
  - `soft`
  - `danger`
  - `nav`

## Files updated
- `operator_desktop/core/theme.py`
- `operator_desktop/ui/common.py`
- `operator_desktop/ui/window.py`
- `operator_desktop/ui/shell.py`
- `operator_desktop/ui/pages/login.py`
- `operator_desktop/ui/pages/dashboard.py`
- `operator_desktop/ui/pages/client_details.py`
- `operator_desktop/ui/pages/teams.py`
- `operator_desktop/ui/pages/compiler.py`
- `operator_desktop/ui/pages/settings.py`
- `operator_desktop/ui/pages/cookies.py`
- `operator_desktop/ui/pages/proxy.py`
- `operator_desktop/ui/pages/instructions.py`
- `operator_desktop/ui/local_desktop.py`

