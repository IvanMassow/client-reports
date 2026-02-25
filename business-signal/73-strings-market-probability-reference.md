# 73 Strings — Market Probability Validation Report
## Machine-Readable Reference for LLM Report Generation

---

## What This Is

A **Market Probability Intelligence Brief** — a self-contained HTML report that tracks belief clusters, probability assessments, and narrative diffusion across a monitored landscape. Built for **73 Strings** using the **Business Signal design system** (slate + blue + gold).

**Live example:** `market-probability-7g4k-2026-02-24.html`
**Design reference:** `bs-innovation-2026-02-25.html` (Business Signal / 73 Intelligence arena report)

---

## Design System: Business Signal (73 Intelligence)

### Colour Palette
| Token | Hex | Usage |
|-------|-----|-------|
| `--slate` | `#181D35` | Topbar, hero, dark sections, footer |
| `--slate-deep` | `#141929` | Hero background, deep sections |
| `--slate-mid` | `#282D45` | Secondary dark backgrounds |
| `--accent` | `#CFA64C` | Gold accent — highlights, borders, labels, question numbers |
| `--accent-light` | `#EDE0B8` | Light gold — callout backgrounds |
| `--pillar` | `#3B6FA8` | Blue primary — Bass Diffusion S-curve, primary borders, exec strip |
| `--pillar-light` | `#E4EDF8` | Light blue — card backgrounds, hover states |
| `--pillar-mid` | `#5688C0` | Mid blue — chart accent |
| `--red` | `#E53E3E` | Critical/gap indicators, blocked overlay dots |
| `--amber` | `#C4920A` | Warning/medium indicators |
| `--green` | `#22C55E` | Positive indicators, present overlay dots |
| `--text` | `#2C2C2C` | Body text |
| `--text-mid` | `#555B66` | Secondary text |
| `--text-muted` | `#8A8F98` | Muted text |
| `--bg` | `#FAFAF8` | Page background |
| `--bg-card` | `#FFFFFF` | Card backgrounds |
| `--border` | `#E8E6E1` | Borders, dividers |

### Typography
| Element | Font | Weight | Size |
|---------|------|--------|------|
| Body text | Inter | 400 | 16px base |
| Hero title | Lora | 700 | 2.4rem |
| Section title | Lora | 700 | 1.5rem |
| Eyebrow labels | Montserrat | 700 | 10px, uppercase, 0.15em spacing |
| Tags/pills | Montserrat / Inter | 600 | 10-11px |
| Table headers | Montserrat | 600 | 0.7rem, uppercase |
| Card titles | Inter | 700 | 0.85rem |
| Prose body | Inter | 400 | 1rem, line-height 1.7 |

### Font Import
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Lora:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
```

---

## Report Structure (Section by Section)

### 1. Topbar (Sticky)
- Height: 52px, slate background
- Left: 73 SVG logo (blue circle with "73" in white) + "73 INTELLIGENCE" text (Montserrat 700) + divider + "MARKET PROBABILITY" product label (muted white)
- Right: REF badge (e.g. "REF: 7G4K") in gold pill + date string
- Logo: `<svg>` with circle fill `#3B6FA8` and white "73" text

### 2. Hero
- Full-width slate-deep section with abstract gradient (radial blue + radial gold), no background image
- Gold-to-blue gradient accent line (3px) across top
- Contains: eyebrow label ("MARKET PROBABILITY INTELLIGENCE"), title (Lora 2.4rem white), deck paragraph, meta pills
- Meta pills: date (blue border), signal strength level (gold border), time horizon, belief count
- Pill variants: `.pill-date` (blue), `.pill-horizon`, `.pill-signal-strength` (gold)

### 3. Executive Strip
- 4-column grid on pillar-blue background
- Cells: EFI Score, Coverage %, Temperature, Grade
- Labels in Montserrat 9px uppercase white/80; values in 18px bold white

### 4. Front Panel / Executive Summary
- Eyebrow: "Part 1 — Front Panel" (Montserrat 700 uppercase, accent gold)
- Prose section with summary text
- `.highlight` callout box (gold left border, soft gold background)
- **Question Board**: Vertical stack of `.question-card` elements
  - `.primary` variant: blue left border + top (main question)
  - `.emerging` variant: gold left border + top (secondary questions)
  - Each card: large probability number (Lora bold, blue/gold) + "HOUSE YES" label + question text + meta row

### 5. Belief Tracking Board
- Eyebrow: "Part 2 — Executive Probability Board"
- Full-width table with columns: ID, Belief, Direction, Phase, Environment
- Direction tags: `.tag-upward` (green), `.tag-volatile` (amber), `.tag-stalled` (grey)
- Phase tags: `.tag-active` (green), `.tag-emerging` (purple)
- Environment tags: `.tag-medium` (amber), `.tag-low` (grey)

### 6. Diagnostics Board (Structural Friction)
- Table with columns: Belief, Friction Type, Overlay coverage (x/3), Rationale
- Friction tags: `.tag-gap` (red — regulatory friction, procedural opacity), `.tag-medium` (amber — conflicting signals), `.tag-stalled` (grey — data absence)

### 7. Belief Analysis (Deep Dives)
- 2-column card grid
- Each card contains:
  - Title with gold dot prefix: "B-T-XXX: Belief Name"
  - Description paragraph
  - **Overlay indicators**: row of colored dots (present=green, blocked=red, silent=grey, absent=light grey) for Hydration, Market, Social, Mechanism
  - Optional mechanism quote in `.card-why` (italic, border-top)
  - Meta tags row: phase, velocity, voice type

### 8. Bass Diffusion Chart (KEY COMPONENT)
- Slate-deep card container (`.bass-chart`)
- Title in gold Montserrat uppercase
- Inline SVG viewBox="0 0 800 300"
- Elements:
  - Grid lines (horizontal dashed rgba white, vertical axis)
  - Y-axis labels: 0%, 25%, 50%, 75%, 100% (white text)
  - X-axis labels: time periods (Day 0 through Day 120)
  - "WE ARE HERE" marker: gold dashed vertical line + label in Montserrat
  - **Cumulative S-curve**: blue (#3B6FA8) path, stroke-width 2.5
  - **Instantaneous bell curve**: gold (#CFA64C) path, stroke-width 2, 0.8 opacity
  - **Area fill under bell curve**: gold gradient fill, 0.15 opacity
  - Phase labels along bottom: DETECTION / VALIDATION / PEAK DIFFUSION / SATURATION (white text)
- Legend below chart: three items with colored bars (blue, gold, white)

### 9. Compliance & Regulatory Deadlines
- 3-column `.steps-grid`
- Each `.step-card`: gold 3px top border, timeframe label (Montserrat uppercase), title, description

### 10. Market Overlay (Polymarket Scan)
- Prose section describing prediction market scan results
- Highlight callout for assessment summary

### 11. Forward Board / Watchlist
- Slate dark section
- 3-column `.watchlist-grid`
- Each item: gold title, description text, probability in gold Montserrat

### 12. Evidence Appendix
- 2-column `.evidence-grid`
- Each `.evidence-item`: ID in Montserrat (blue), description text

### 13. Sources & Methodology
- Unordered `.source-list` with gold dot bullets
- Italicised methodology note

### 14. Footer
- Slate-deep background
- Brand text: "73 INTELLIGENCE — Market Probability" (Montserrat)
- Note: "Prepared by Noah Wire Services for 73 Strings | Date | Classification"
- "Powered by NOAH" badge

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
| `.overlay-dot.present` | Data available | Green (#22C55E) |
| `.overlay-dot.blocked` | Data blocked | Red (#E53E3E) |
| `.overlay-dot.silent` | No signal | Grey (#8A8F98) |
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
  "signal_strength": "Medium"
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
    "signal_strength": "Medium"
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
    "cumulative": "S-curve (blue #3B6FA8)",
    "instantaneous": "Bell curve (gold #CFA64C) with area fill"
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
2. **Design system**: Copy CSS from `bs-innovation-2026-02-25.html` (Business Signal / 73 Intelligence)
3. **Bass Diffusion chart**: Inline SVG with two paths (cumulative S-curve in blue + instantaneous bell curve in gold + area fill)
4. **Key adaptation from Business Signal**: Replace arena/pillar structure with belief cluster tracking; replace perception dashboard with question board; keep similar card/table patterns
5. **Branding**: "73 INTELLIGENCE — Market Probability" in topbar and footer. "Prepared for 73 Strings" in footer. "Powered by NOAH" badge.

---

## Differences Between Products

| Aspect | Business Signal (Arena) | Market Probability (This) |
|--------|------------------------|--------------------------|
| **Client** | 73 Strings (corporate) | 73 Strings (market) |
| **Design** | Slate + gold + blue pillar | Slate + gold + blue pillar (same family) |
| **Fonts** | Inter + Lora + Montserrat | Inter + Lora + Montserrat (same) |
| **Core unit** | Arenas (pillars) | Belief clusters |
| **Probability** | Forward outlook predictions | Question board (House YES/NO) |
| **Chart** | Prediction tiles | Bass Diffusion (narrative diffusion) |
| **Unique** | Standing context + signals | Diagnostics board, overlay indicators, Bass Diffusion SVG |
| **Hero** | Abstract gradient (no image) | Abstract gradient (no image) |

---

## File Locations
| File | Purpose |
|------|---------|
| `business-signal/market-probability-7g4k-2026-02-24.html` | This report (73 Strings Market Probability) |
| `business-signal/bs-innovation-2026-02-25.html` | Business Signal arena report (same 73 Intelligence design family) |
| `business-signal/poller.py` | Business Signal template generator (Python) |
| `business-signal/methodology.html` | Business Signal methodology page |
