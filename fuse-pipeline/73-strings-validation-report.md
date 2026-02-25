# 73 Strings — Market Probability Validation Report
## Machine-Readable Reference for LLM Report Generation

---

## What This Is

A **Market Probability Intelligence Brief** — a self-contained HTML report that tracks belief clusters, probability assessments, and narrative diffusion across a monitored landscape. Built for **73 Strings** using the **Fuse Pipeline design system** (dark green + yellow).

**Live example:** `market-probability-7g4k-2026-02-24.html`
**Design reference:** `bionic-cisco-2026-02-24.html` (Fuse Pipeline / Bionic Intelligence)
**Business Signal reference:** `../business-signal/bs-innovation-2026-02-25.html` (arena/pillar structure)

---

## Design System: Fuse Pipeline

### Colour Palette
| Token | Hex | Usage |
|-------|-----|-------|
| `--fp-yellow` | `#FEE000` | Primary accent, highlights, chart lines, CTA |
| `--fp-green-dark` | `#013124` | Topbar, exec strip, dark sections, table headers |
| `--fp-green-deep` | `#0D2E25` | Hero background, footer |
| `--fp-green-mid` | `#14342C` | Eyebrow text on light backgrounds |
| `--fp-green-text` | `#1B4136` | Text in highlighted callouts |
| `--fp-lime` | `#C0D357` | Secondary chart line, emerging indicators |
| `--fp-teal` | `#34584e` | Supporting dark elements |
| `--fp-charcoal` | `#30302E` | Body text |
| `--fp-grey-bg` | `#F7F7F5` | Alternating section backgrounds |
| `--fp-grey-200` | `#E5E5E3` | Borders, dividers |
| `--fp-red` | `#DC2626` | Critical/gap indicators |
| `--fp-amber` | `#D97706` | Warning/medium indicators |
| `--fp-green` | `#059669` | Positive/good indicators |
| `--fp-blue` | `#1055C9` | Info/unknown indicators |
| `--fp-purple` | `#7C3AED` | Emerging phase indicators |

### Typography
| Element | Font | Weight | Size |
|---------|------|--------|------|
| Body text | Inter | 400 | 16px base |
| Hero title | Inter | 800 | 2.6rem |
| Section title | Inter | 800 | 1.65rem |
| Eyebrow labels | JetBrains Mono | 700 | 11px, uppercase, 0.15em spacing |
| Tags/pills | JetBrains Mono | 600 | 10-11px |
| Table headers | Inter | 600 | 0.75rem, uppercase |
| Card titles | Inter | 700 | 0.85rem |
| Prose body | Inter | 400 | 1rem, line-height 1.75 |

### Font Import
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
```

---

## Report Structure (Section by Section)

### 1. Topbar (Sticky)
- Height: 54px, dark green background with 95% opacity + backdrop blur
- Left: Noah logo (two-bar icon — white + yellow segments) + "Noah **intelligence**" text + divider + "MARKET PROBABILITY" product label (yellow, mono)
- Right: REF badge (e.g. "REF: 7G4K") in yellow pill + date string
- Logo icon: Two stacked bars with `.seg-white` and `.seg-yellow` spans

### 2. Hero
- Full-width dark green section with background image (hero-skyline.png), gradient overlay
- Yellow 3px bottom border
- Contains: label bar ("Market Probability Intelligence"), title (2.6rem), deck paragraph, meta pills
- Meta pills: date, confidence level, time horizon, belief count
- Pill variants: `.date`, `.medium`, `.horizon`, `.broad`, `.positive`, `.stable`

### 3. Executive Strip
- 4-column grid on dark green, yellow 2px top border
- Cells: EFI Score, Coverage %, Temperature, Grade
- Labels in mono 9px uppercase; values in 15px bold yellow

### 4. Front Panel / Executive Summary
- Eyebrow: "Part 1 — Front Panel"
- Prose section with summary text
- `.highlight` callout box (yellow left border, soft yellow background)
- **Question Board**: Vertical stack of `.question-card` elements
  - `.primary` variant: yellow left border (main question)
  - `.emerging` variant: lime left border (secondary questions)
  - Each card: large probability number + "House YES" label + question text + meta row

### 5. Belief Tracking Board
- Eyebrow: "Part 2 — Executive Probability Board"
- Alternating grey background section
- Full-width table with columns: ID, Belief, Direction, Phase, Environment
- Direction tags: `.tag-upward`, `.tag-volatile`, `.tag-stalled`
- Phase tags: `.tag-active`, `.tag-emerging`
- Environment tags: `.tag-medium`, `.tag-low`

### 6. Diagnostics Board (Structural Friction)
- Table with columns: Belief, Friction Type, Overlay coverage (x/3), Rationale
- Friction tags: `.tag-gap` (regulatory friction, procedural opacity), `.tag-medium` (conflicting signals), `.tag-stalled` (data absence)

### 7. Belief Analysis (Deep Dives)
- 2-column card grid
- Each card contains:
  - Title with yellow dot prefix: "B-T-XXX: Belief Name"
  - Description paragraph
  - **Overlay indicators**: row of colored dots (present=green, blocked=red, silent=grey, absent=light grey) for Hydration, Market, Social, Mechanism
  - Optional mechanism quote in `.card-why` (italic, border-top)
  - Meta tags row: phase, velocity, voice type

### 8. Bass Diffusion Chart (KEY COMPONENT)
- Dark green card container (`.bass-chart`)
- Title in yellow mono uppercase
- Inline SVG viewBox="0 0 800 300"
- Elements:
  - Grid lines (horizontal dashed, vertical axis)
  - Y-axis labels: 0%, 25%, 50%, 75%, 100%
  - X-axis labels: time periods (Day 0 through Day 120, or quarters)
  - "WE ARE HERE" marker: yellow dashed vertical line + label in JetBrains Mono
  - **Cumulative S-curve**: yellow (#FEE000) path, stroke-width 2.5
  - **Instantaneous bell curve**: lime (#C0D357) path, stroke-width 2, 0.8 opacity
  - **Area fill under bell curve**: lime gradient fill, 0.15 opacity
  - Phase labels along bottom: DETECTION / VALIDATION / PEAK DIFFUSION / SATURATION
- Legend below chart: three items with colored bars

### 9. Compliance & Regulatory Deadlines
- 3-column `.steps-grid`
- Each `.step-card`: yellow 3px top border, timeframe label (mono uppercase), title, description

### 10. Market Overlay (Polymarket Scan)
- Prose section describing prediction market scan results
- Highlight callout for assessment summary

### 11. Forward Board / Watchlist
- Dark section (`.section-dark`)
- 3-column `.watchlist-grid`
- Each item: yellow title, description text, probability in lime mono

### 12. Evidence Appendix
- 2-column `.evidence-grid`
- Each `.evidence-item`: ID in mono (green), description text

### 13. Sources & Methodology
- Alternating grey section
- Unordered `.source-list` with yellow dot bullets
- Italicised methodology note

### 14. Footer
- Deep green background
- Brand text: "Noah **intelligence** — Market Probability"
- Note: "Prepared by Noah Wire Services for 73 Strings | Date | Classification"

---

## Tag/Badge System

### Direction Tags
| Class | Label | Colours |
|-------|-------|---------|
| `.tag-upward` | Upward | Green bg/text |
| `.tag-volatile` | Volatile | Amber bg/text |
| `.tag-stalled` | Stalled | Grey bg/text with border |

### Phase Tags
| Class | Label | Colours |
|-------|-------|---------|
| `.tag-active` | Active | Green bg/text |
| `.tag-emerging` | Emerging | Purple bg/text |

### Friction/Fit Tags
| Class | Label | Colours |
|-------|-------|---------|
| `.tag-gap` | Gap / Regulatory friction | Red bg/text |
| `.tag-medium` | Medium / Conflicting signals | Amber bg/text |
| `.tag-partial` | Partial | Amber bg/text |
| `.tag-good` | Good | Green bg/text |

### Overlay Indicator Dots
| Class | State | Colour |
|-------|-------|--------|
| `.overlay-dot.present` | Data available | Green (#059669) |
| `.overlay-dot.blocked` | Data blocked | Red (#DC2626) |
| `.overlay-dot.silent` | No signal | Grey (#9CA3AF) |
| `.overlay-dot.absent` | Not attempted | Light grey (#D1D1CF) |

---

## Data Model (What the Report Contains)

### Cycle Metadata
```json
{
  "ref": "7G4K",
  "date": "2026-02-24",
  "scope": "Global",
  "horizon": "48-72 hours",
  "efi_score": 0,
  "coverage_pct": 33,
  "temperature": "Calm",
  "grade": "D",
  "confidence": "Medium"
}
```

### Question Board
```json
[
  {
    "type": "primary",
    "question": "Will regulatory attention on Compass increase within 48-72 hours?",
    "house_yes": 73,
    "house_no": 27,
    "market": null,
    "confidence": "Medium"
  },
  {
    "type": "emerging",
    "question": "Will Homes.com adoption and rollout signalling intensify?",
    "house_yes": 56,
    "house_no": 44,
    "market": null
  }
]
```

### Belief Tracking Board
```json
[
  {
    "id": "B-T-001",
    "label": "Compass regulation focus",
    "direction": "Upward",
    "phase": "Active",
    "environment": "Medium",
    "velocity": "Stable",
    "dominant_voice": "Mixed",
    "evidence_ids": ["EV-001", "EV-002", "EV-003", "EV-004", "EV-005"],
    "overlay": {
      "hydration": "Present",
      "market": "Blocked",
      "social": "Silent",
      "mechanism": "Present"
    },
    "friction": ["regulatory_friction", "procedural_opacity"],
    "overlay_coverage": "2/3"
  }
]
```

### Bass Diffusion Parameters
```json
{
  "p_innovation": 0.05,
  "q_imitation": 0.55,
  "current_phase": "Detection/Validation boundary",
  "days_to_peak": "60-90",
  "signal_type": "Steady with procedural friction",
  "curves": {
    "cumulative": "S-curve (yellow #FEE000)",
    "instantaneous": "Bell curve (lime #C0D357) with area fill"
  },
  "phases": ["Detection", "Validation", "Peak Diffusion", "Saturation"]
}
```

### Evidence Ledger Entry
```json
{
  "id": "EV-001",
  "summary": "Compass-Anywhere Real Estate merger completion",
  "source": "PRNewswire",
  "tier": "B",
  "beliefs_linked": ["B-T-001", "B-T-005"]
}
```

---

## How to Regenerate This Report

1. **Content source**: RSS feed at `https://73strings.makes.news/` — Market Probability Intelligence Brief articles
2. **Design system**: Copy CSS from `bionic-cisco-2026-02-24.html` (Fuse Pipeline)
3. **Bass Diffusion chart**: Inline SVG with two paths (cumulative S-curve + instantaneous bell curve + area fill)
4. **Key adaptation from Bionic Cisco**: Replace "Pressure Outlook" framing with "Market Probability" framing; replace 5 pressure vectors with N belief clusters; keep Bass Diffusion chart but relabel axes for belief diffusion timeline
5. **Key adaptation from Business Signal**: The question board, belief tracking table, and diagnostics board are unique to Market Probability — Business Signal uses arena cards, perception dashboard, and standing context instead
6. **Branding**: "Noah **intelligence** — Market Probability" in topbar and footer. "Prepared for 73 Strings" in footer note.

---

## File Locations
| File | Purpose |
|------|---------|
| `fuse-pipeline/market-probability-7g4k-2026-02-24.html` | This report (73 Strings Market Probability) |
| `fuse-pipeline/bionic-cisco-2026-02-24.html` | Fuse Pipeline design system source (Cisco report) |
| `fuse-pipeline/bionic-xreal-2026-02-24.html` | Fuse Pipeline design system source (xReal report) |
| `fuse-pipeline/hero-skyline.png` | Hero background image |
| `fuse-pipeline/og-image.png` | OpenGraph social card image |
| `business-signal/bs-innovation-2026-02-25.html` | Business Signal arena report (different product, same Noah brand) |
| `business-signal/poller.py` | Business Signal template generator (Python) |
| `business-signal/methodology.html` | Business Signal methodology page |

---

## Differences Between Products

| Aspect | Fuse Pipeline (Bionic) | Business Signal | Market Probability (This) |
|--------|----------------------|-----------------|--------------------------|
| **Client** | Cisco, xReal, etc. | 73 Strings (corporate) | 73 Strings (market) |
| **Design** | Dark green + yellow | Slate + gold + blue pillar | Dark green + yellow |
| **Fonts** | Inter + JetBrains Mono | Inter + Lora + Montserrat | Inter + JetBrains Mono |
| **Core unit** | Pressure vectors | Arenas (pillars) | Belief clusters |
| **Probability** | Watchlist probabilities | Forward outlook predictions | Question board (House YES/NO) |
| **Chart** | Bass Diffusion (adoption) | Prediction tiles | Bass Diffusion (narrative diffusion) |
| **Unique** | Fit assessment tables | Standing context + signals | Diagnostics board, overlay indicators |
| **Hero** | Background image + gradient | Abstract gradient (no image) | Background image + gradient |
