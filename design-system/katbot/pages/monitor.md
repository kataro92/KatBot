# Monitor page override

User direction (2026-08-18): **glassmorphism + pastel**, not the dark-tech MASTER palette.

Style still follows [ui-ux-pro-max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) Glassmorphism: `backdrop-filter: blur(16px)`, translucent cards, 1px light border, vibrant layered background, Z-depth. Light-mode glass opacity ≥ 0.78 for 4.5:1 text.

## Tokens

| Role | Hex / value | CSS |
|------|-------------|-----|
| Background wash | `#F6F0FF` + blobs | `--color-background` |
| Foreground | `#1E293B` | `--color-foreground` |
| Primary / CTA | `#8B9CFF` periwinkle | `--color-primary` |
| Accent mint | `#5EC8B6` | `--color-accent` |
| Pink | `#F9A8D4` | `--color-pink` |
| Lavender | `#C4B5FD` | `--color-lavender` |
| Temp series | `#0F766E` (solid) | `--color-temp` |
| Humidity series | `#2563EB` (dashed) | `--color-hum` |
| Glass fill | `rgba(255,255,255,0.78)` | `--glass-bg` |
| Glass border | `rgba(255,255,255,0.88)` | `--glass-border` |
| Blur | `16px` | `--blur-amount` |
| Destructive | `#DC2626` | `--color-destructive` |
| Ring | `#7C6CFF` | `--color-ring` |

## Typography

**Be Vietnam Pro** (headings) + **Inter** (body). Both include a Vietnamese subset; Be Vietnam Pro uses adaptive diacritics. Avoid Fredoka/rounded display faces — they crowd tone marks (ă, ê, ơ, ư). Body line-height ≥ 1.65.

## Chart

Streaming area/line: solid mint for temperature, dashed sky for humidity. Never color-only. Current values also in metric cards.
