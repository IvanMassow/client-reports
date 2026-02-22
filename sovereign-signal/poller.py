#!/usr/bin/env python3
"""
Sovereign Signal — Daily RSS Poller & Dashboard Generator

Polls the RSS feed for the 5 daily Sovereign Standing Briefs,
parses their content, generates per-pillar HTML reports and
updates the main dashboard index.html.

Usage:
  python3 poller.py              # Poll once, generate if all 5 ready
  python3 poller.py --wait       # Poll every 5 min until all 5 arrive
  python3 poller.py --date 2026-02-22  # Target a specific date
"""

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

# ─── Configuration ────────────────────────────────────────────────

RSS_URL = "https://sovereignsignal.makes.news/section/6997b02067330856c7668f5f/rss.xml"
POLL_INTERVAL = 300  # 5 minutes
MAX_POLLS = 72       # 6 hours max wait

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# ─── Pillar Definitions ──────────────────────────────────────────

PILLARS = {
    "softpower": {
        "name": "Soft Power & Cultural Standing",
        "short": "Soft Power",
        "headline": "SOVEREIGN STANDING BRIEF — SOFT POWER & CULTURAL STANDING — UK",
        "color": "#7C5295",
        "color_light": "#F0E6F6",
        "color_mid": "#9568B0",
        "slug": "softpower",
        "keywords": ["soft power", "cultural"],
    },
    "defence": {
        "name": "Defence & Strategic Credibility",
        "short": "Defence",
        "headline": "SOVEREIGN STANDING BRIEF — DEFENCE & STRATEGIC CREDIBILITY — UK",
        "color": "#4A6FA5",
        "color_light": "#E4EDF6",
        "color_mid": "#5E88BE",
        "slug": "defence",
        "keywords": ["defence", "defense", "strategic credibility", "military"],
    },
    "economic": {
        "name": "Economic & Business Leadership",
        "short": "Economic",
        "headline": "SOVEREIGN STANDING BRIEF — ECONOMIC & BUSINESS LEADERSHIP — UK",
        "color": "#3D8B6E",
        "color_light": "#E2F2EB",
        "color_mid": "#52A688",
        "slug": "economic",
        "keywords": ["economic", "business", "competence"],
    },
    "diplomatic": {
        "name": "Diplomatic & Global Leadership",
        "short": "Diplomatic",
        "headline": "SOVEREIGN STANDING BRIEF — DIPLOMATIC & GLOBAL LEADERSHIP — UK",
        "color": "#B08830",
        "color_light": "#F8F0DA",
        "color_mid": "#C9A040",
        "slug": "diplomatic",
        "keywords": ["diplomatic", "global leadership", "diplomacy"],
    },
    "trust": {
        "name": "Trust, Stability & Systemic Reliability",
        "short": "Trust",
        "headline": "SOVEREIGN STANDING BRIEF — TRUST, STABILITY & SYSTEMIC RELIABILITY — UK",
        "color": "#B85C4A",
        "color_light": "#F8E8E4",
        "color_mid": "#D0715E",
        "slug": "trust",
        "keywords": ["trust", "stability", "governance", "systemic", "reliability"],
    },
}


# ─── RSS Fetching ─────────────────────────────────────────────────

def fetch_rss():
    """Fetch and parse the RSS feed, return list of item dicts."""
    req = urllib.request.Request(RSS_URL, headers={"User-Agent": "SovereignSignal/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        xml_bytes = resp.read()

    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.findall(".//item"):
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        desc = item.findtext("description", "")
        guid = item.findtext("guid", "")
        pub_date = item.findtext("pubDate", "")

        # Decode HTML entities in description
        desc = html.unescape(desc)

        items.append({
            "title": title,
            "link": link,
            "description": desc,
            "guid": guid,
            "pub_date": pub_date,
        })

    return items


def extract_date_from_title(title):
    """Extract YYYY-MM-DD date from title like '... | 2026-02-22 [ZKPL]'"""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", title)
    return m.group(1) if m else None


def extract_ref_from_title(title):
    """Extract reference code from title like '... [ZKPL]'"""
    m = re.search(r"\[([A-Z0-9]{4})\]", title)
    return m.group(1) if m else None


def classify_pillar(title):
    """Match an RSS item title to one of our 5 pillars."""
    title_lower = title.lower()
    for key, pillar in PILLARS.items():
        for kw in pillar["keywords"]:
            if kw in title_lower:
                return key
    return None


def filter_items_for_date(items, target_date):
    """Filter RSS items to those matching the target date string."""
    return [i for i in items if extract_date_from_title(i["title"]) == target_date]


# ─── Content Parsing ──────────────────────────────────────────────

def parse_report_content(desc_html):
    """
    Parse the HTML description from the RSS feed to extract structured data:
    - Executive summary
    - Sovereign Perception Dashboard (propositions + scores)
    - Trend Matrix
    - Strength signals
    - Vulnerability signals
    - Strategic priorities
    - Standing assessment / conclusion
    """
    data = {
        "executive_summary": "",
        "perception_dashboard": [],
        "trends": [],
        "strength_signals": [],
        "vulnerability_signals": [],
        "priorities": [],
        "conclusion": "",
        "score": None,
        "posture": None,
        "trend_count": 0,
        "strength_count": 0,
        "vuln_count": 0,
    }

    # Extract executive summary
    exec_match = re.search(
        r"<h2[^>]*>.*?Executive Summary.*?</h2>(.*?)(?=<h2|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if exec_match:
        summary_html = exec_match.group(1)
        # Strip tags for plain text
        data["executive_summary"] = re.sub(r"<[^>]+>", "", summary_html).strip()

    # Extract perception dashboard table
    # Look for proposition rows with percentages
    prop_pattern = re.compile(
        r"P-SS-\d+\s*\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]*)\|",
        re.IGNORECASE
    )
    for m in prop_pattern.finditer(desc_html):
        data["perception_dashboard"].append({
            "proposition": m.group(1).strip(),
            "global_view": m.group(2).strip(),
            "sovereign_view": m.group(3).strip(),
            "confidence": m.group(4).strip(),
            "arena": m.group(5).strip(),
        })

    # Extract trend count from Trend Matrix
    trend_matches = re.findall(r"T\d+\s*\|", desc_html)
    data["trend_count"] = len(trend_matches)

    # Extract strength signals
    strength_section = re.search(
        r"Sovereign Strength Signals(.*?)(?=<h2|Sovereign Vulnerability|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if strength_section:
        ss_matches = re.findall(r"SS-\d+", strength_section.group(1))
        data["strength_count"] = len(ss_matches)
        data["strength_signals"] = ss_matches

    # Extract vulnerability signals
    vuln_section = re.search(
        r"Sovereign Vulnerability Signals(.*?)(?=<h2|Structural Contradictions|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if vuln_section:
        vs_matches = re.findall(r"VS-\d+|V-T\d+", vuln_section.group(1))
        data["vuln_count"] = len(vs_matches)
        data["vulnerability_signals"] = vs_matches

    # Extract conclusion
    conclusion_match = re.search(
        r"<h2[^>]*>.*?Conclusion.*?</h2>(.*?)(?=<h2|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if conclusion_match:
        data["conclusion"] = re.sub(r"<[^>]+>", "", conclusion_match.group(1)).strip()

    # Try to extract a score from the standing assessment
    score_match = re.search(r"(?:score|standing)[:\s]*(\d{1,3})\s*/\s*100", desc_html, re.IGNORECASE)
    if score_match:
        data["score"] = int(score_match.group(1))

    # Try to extract posture
    posture_match = re.search(
        r"(?:perceived as|posture[:\s]*|standing[:\s]*)\s*(strong|mixed|moderate|weak|declining)",
        desc_html, re.IGNORECASE
    )
    if posture_match:
        data["posture"] = posture_match.group(1).capitalize()

    # If no score found, estimate from perception dashboard percentages
    if data["score"] is None and data["perception_dashboard"]:
        scores = []
        for p in data["perception_dashboard"]:
            # Try all fields for percentage values
            for field in ["proposition", "global_view", "sovereign_view", "confidence"]:
                val = p.get(field, "").replace("%", "").strip()
                try:
                    v = float(val)
                    if 0 <= v <= 100:
                        scores.append(v)
                        break
                except ValueError:
                    continue
        if scores:
            # Average the sovereign-view-like scores, scale slightly
            data["score"] = int(sum(scores) / len(scores) * 1.15)
            data["score"] = min(data["score"], 100)

    # If still no score, try to find any percentage pattern in the text
    if data["score"] is None:
        all_pcts = re.findall(r"(\d{1,3})%", desc_html)
        valid_pcts = [int(p) for p in all_pcts if 20 <= int(p) <= 95]
        if valid_pcts:
            data["score"] = int(sum(valid_pcts) / len(valid_pcts))

    # Default posture based on score
    if data["score"] is not None:
        if data["posture"] is None:
            if data["score"] >= 70:
                data["posture"] = "Strong"
            elif data["score"] >= 50:
                data["posture"] = "Mixed"
            else:
                data["posture"] = "Weak"
    else:
        # Absolute fallback: assign a neutral score
        data["score"] = 50
        if data["posture"] is None:
            data["posture"] = "Mixed"

    return data


# ─── Data Persistence ─────────────────────────────────────────────

def load_history():
    """Load the historical scores JSON."""
    history_file = DATA_DIR / "history.json"
    if history_file.exists():
        with open(history_file) as f:
            return json.load(f)
    return {}


def save_history(history):
    """Save the historical scores JSON."""
    history_file = DATA_DIR / "history.json"
    with open(history_file, "w") as f:
        json.dump(history, f, indent=2)


def save_day_data(target_date, pillar_data):
    """Save the parsed data for a specific date."""
    day_file = DATA_DIR / f"{target_date}.json"
    with open(day_file, "w") as f:
        json.dump(pillar_data, f, indent=2)

    # Update history
    history = load_history()
    if target_date not in history:
        history[target_date] = {}
    for key, pdata in pillar_data.items():
        history[target_date][key] = {
            "score": pdata.get("score"),
            "posture": pdata.get("posture"),
            "trend_count": pdata.get("trend_count", 0),
            "strength_count": pdata.get("strength_count", 0),
            "vuln_count": pdata.get("vuln_count", 0),
        }
    save_history(history)
    return history


# ─── Dashboard Generation ─────────────────────────────────────────

def generate_dashboard(target_date, pillar_data, history):
    """Generate/update the index.html dashboard with real data."""

    # Calculate composite score (only from pillars with valid scores)
    scores = [p["score"] for p in pillar_data.values() if p.get("score") is not None]
    composite = int(sum(scores) / len(scores)) if scores else 0

    # Calculate deltas from previous day
    dates = sorted(history.keys())
    prev_date = None
    for d in dates:
        if d < target_date:
            prev_date = d

    deltas = {}
    prev_composite = None
    if prev_date and prev_date in history:
        prev_scores = []
        for key in PILLARS:
            prev_s = history.get(prev_date, {}).get(key, {}).get("score")
            curr_s = pillar_data.get(key, {}).get("score")
            if prev_s is not None and curr_s is not None:
                deltas[key] = curr_s - prev_s
                prev_scores.append(prev_s)
        if prev_scores:
            prev_composite = int(sum(prev_scores) / len(prev_scores))

    composite_delta = composite - prev_composite if prev_composite is not None else None

    # Determine composite posture
    if composite >= 70:
        composite_posture = "Strong"
    elif composite >= 50:
        composite_posture = "Mixed"
    else:
        composite_posture = "Weak"

    # Format date for display
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    display_date = dt.strftime("%d %B %Y")

    # Build previous/next date links
    prev_link = ""
    next_link = ""
    if prev_date:
        prev_link = f"data/{prev_date}.json"  # We'll handle this in JS

    # ─── Generate HTML ───
    template = _build_dashboard_html(
        target_date=target_date,
        display_date=display_date,
        composite=composite,
        composite_delta=composite_delta,
        composite_posture=composite_posture,
        pillar_data=pillar_data,
        deltas=deltas,
        dates=dates,
    )

    output_path = SCRIPT_DIR / "index.html"
    with open(output_path, "w") as f:
        f.write(template)

    print(f"  Dashboard written to {output_path}")

    # Also write a summary.json for potential API consumers
    summary = {
        "date": target_date,
        "composite_score": composite,
        "composite_posture": composite_posture,
        "composite_delta": composite_delta,
        "pillars": {},
    }
    for key, pdata in pillar_data.items():
        summary["pillars"][key] = {
            "name": PILLARS[key]["name"],
            "score": pdata.get("score"),
            "posture": pdata.get("posture"),
            "delta": deltas.get(key),
            "trend_count": pdata.get("trend_count", 0),
            "strength_count": pdata.get("strength_count", 0),
            "vuln_count": pdata.get("vuln_count", 0),
            "executive_summary": pdata.get("executive_summary", "")[:200],
        }
    summary_path = DATA_DIR / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Summary written to {summary_path}")


def _delta_html(delta, is_hero=False):
    """Generate delta display HTML."""
    if delta is None:
        return '<span class="flat">&mdash; First cycle</span>' if is_hero else "&mdash;"
    if delta > 0:
        cls = "up"
        arrow = "&#9650;"  # ▲
        text = f"+{delta}"
    elif delta < 0:
        cls = "down"
        arrow = "&#9660;"  # ▼
        text = str(delta)
    else:
        cls = "flat"
        arrow = "&mdash;"
        text = "0"
    if is_hero:
        return f'<span class="{cls}">{arrow} {text} from yesterday</span>'
    return f'<span class="{cls}">{arrow} {text}</span>'


def _posture_class(posture):
    if not posture:
        return "mixed"
    p = posture.lower()
    if p in ("strong",):
        return "strong"
    if p in ("weak", "declining"):
        return "weak"
    return "mixed"


def _get_dashboard_css():
    """Return the full dashboard CSS. Extracted to keep template generation clean."""
    css_path = SCRIPT_DIR / "dashboard.css"
    if css_path.exists():
        with open(css_path) as f:
            return f.read()
    # Inline fallback — read from the original index.html
    index_path = SCRIPT_DIR / "index.html"
    if index_path.exists():
        with open(index_path) as f:
            content = f.read()
        m = re.search(r"<style>(.*?)</style>", content, re.DOTALL)
        if m:
            return m.group(1)
    return "/* CSS not found */"


def _build_dashboard_html(target_date, display_date, composite, composite_delta,
                          composite_posture, pillar_data, deltas, dates):
    """Build the full index.html dashboard from scratch using data."""

    posture_cls = _posture_class(composite_posture)
    composite_delta_html = _delta_html(composite_delta, is_hero=True)

    # Build pillar score cells
    pillar_score_cells = ""
    for key, pillar in PILLARS.items():
        pdata = pillar_data.get(key, {})
        score = pdata.get("score")
        score_display = score if score is not None else "—"
        post = pdata.get("posture") or "—"
        delta = deltas.get(key)
        delta_str = _delta_html(delta)
        delta_cls = "up" if delta and delta > 0 else "down" if delta and delta < 0 else "flat"
        cell_cls = "delta-up" if delta and delta > 0 else "delta-down" if delta and delta < 0 else ""
        pillar_score_cells += f'''
      <a class="pillar-score-cell{" " + cell_cls if cell_cls else ""}" data-pillar="{key}" href="#tile-{key}">
        <div class="pillar-score-name">{pillar["name"]}</div>
        <div class="pillar-score-num">{score_display}</div>
        <div class="pillar-score-delta {delta_cls}">{delta_str}</div>
        <div class="pillar-score-posture">{post}</div>
      </a>'''

    # Build pillar tiles
    pillar_tiles_html = ""
    for key, pillar in PILLARS.items():
        pdata = pillar_data.get(key, {})
        score = pdata.get("score")
        score_display = score if score is not None else "—"
        post = pdata.get("posture") or "—"
        delta = deltas.get(key)
        delta_text = f"+{delta}" if delta and delta > 0 else str(delta) if delta else "&mdash; First cycle"
        delta_color = "var(--green)" if delta and delta > 0 else "var(--red)" if delta and delta < 0 else "var(--text-muted)"
        summary = pdata.get("executive_summary", "")
        if not summary or summary.startswith("[Section"):
            summary = "Assessment pending — report data will populate when available."
        summary = summary[:250]
        strength_count = pdata.get("strength_count", 0)
        vuln_count = pdata.get("vuln_count", 0)
        trend_count = pdata.get("trend_count", 0)
        conf = "Med" if score else "—"
        report_file = f"uk-{key}-{target_date}.html"
        href = report_file if (SCRIPT_DIR / report_file).exists() else "#"

        pillar_tiles_html += f'''
      <a class="pillar-tile" data-pillar="{key}" id="tile-{key}" href="{href}">
        <div class="pillar-tile-header">
          <div class="pillar-tile-left">
            <span class="pillar-tile-tag">{pillar["short"]}</span>
            <div class="pillar-tile-name">{pillar["name"]}</div>
          </div>
          <div class="pillar-tile-score-box">
            <div class="pillar-tile-score">{score_display}</div>
            <div class="pillar-tile-score-label">Score</div>
            <div class="pillar-tile-delta flat" style="color:{delta_color}">{delta_text}</div>
          </div>
        </div>
        <div class="pillar-tile-body">
          <p class="pillar-tile-summary">{summary}</p>
          <div class="pillar-tile-metrics">
            <div class="ptm"><div class="ptm-val">{strength_count}</div><div class="ptm-label">Strengths</div></div>
            <div class="ptm"><div class="ptm-val">{vuln_count}</div><div class="ptm-label">Vulns</div></div>
            <div class="ptm"><div class="ptm-val">{trend_count}</div><div class="ptm-label">Trends</div></div>
            <div class="ptm"><div class="ptm-val" style="color:var(--amber)">{conf}</div><div class="ptm-label">Confidence</div></div>
          </div>
        </div>
        <div class="pillar-tile-footer">
          <span class="pillar-tile-cta">View Full Report &rarr;</span>
          <span class="pillar-tile-time">{"Updated" if key in pillar_data else "Pending"}</span>
        </div>
      </a>'''

    # Build signals summary cards (compact, one per pillar)
    signals_html = ""
    total_strengths = 0
    total_vulns = 0
    for key, pdata in pillar_data.items():
        pillar = PILLARS[key]
        sc = pdata.get("strength_count", 0)
        vc = pdata.get("vuln_count", 0)
        total_strengths += sc
        total_vulns += vc
        signals_html += f'''
      <div class="signal-card">
        <div class="signal-card-pillar" style="background:{pillar["color_light"]};color:{pillar["color"]}">{pillar["short"]}</div>
        <div class="signal-card-stats">
          <div class="signal-stat">
            <div class="signal-stat-num strength">{sc}</div>
            <div class="signal-stat-label">Strengths</div>
          </div>
          <div class="signal-stat">
            <div class="signal-stat-num vuln">{vc}</div>
            <div class="signal-stat-label">Vulns</div>
          </div>
        </div>
      </div>'''

    if not signals_html:
        signals_html = '''
      <div class="trend-note">Signal data will populate as reports are processed.</div>'''

    signals_meta = f"{total_strengths} Strengths &middot; {total_vulns} Vulnerabilities"

    # Date nav
    prev_date_link = ""
    for d in sorted(dates):
        if d < target_date:
            prev_date_link = d

    # Read CSS from template file
    css_path = SCRIPT_DIR / "dashboard.css"
    if css_path.exists():
        with open(css_path) as f:
            css = f.read()
    else:
        # Use the CSS from the original index.html if available
        css = _get_dashboard_css()

    # Build score-block delta HTML
    if composite_delta is None:
        sb_delta_cls = "flat"
        sb_delta_content = "&mdash; First cycle"
    elif composite_delta > 0:
        sb_delta_cls = "up"
        sb_delta_content = f"&#9650; +{composite_delta} from yesterday"
    elif composite_delta < 0:
        sb_delta_cls = "down"
        sb_delta_content = f"&#9660; {composite_delta} from yesterday"
    else:
        sb_delta_cls = "flat"
        sb_delta_content = "&mdash; 0 from yesterday"

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sovereign Signal — UK Standing Intelligence</title>
<meta property="og:title" content="Sovereign Signal — UK Standing Intelligence">
<meta property="og:description" content="National standing intelligence report — five-pillar assessment of the United Kingdom's external positioning.">
<meta property="og:image" content="https://ivanmassow.github.io/client-reports/sovereign-signal/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Sovereign Signal — UK Standing Intelligence">
<meta name="twitter:description" content="National standing intelligence report">
<meta name="twitter:image" content="https://ivanmassow.github.io/client-reports/sovereign-signal/og-image.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Lora:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
{css}
</style>
</head>
<body>

<div class="topbar">
  <div class="topbar-left">
    <div class="topbar-logo">NOAH</div>
    <div class="topbar-divider"></div>
    <span class="topbar-brand">Sovereign Signal</span>
  </div>
  <div class="topbar-right">
    <nav class="topbar-nav">
      <a href="#" class="active">Dashboard</a>
      <a href="#pillars">Pillars</a>
      <a href="#signals">Signals</a>
    </nav>
    <span class="topbar-date" id="topbar-date">{display_date}</span>
  </div>
</div>

<div class="hero">
  <div class="hero-bg"></div>
  <div class="hero-inner">
    <div class="hero-left">
      <div class="hero-eyebrow">United Kingdom</div>
      <h1 class="hero-title">Sovereign<br><span style="color:var(--accent)">Signal</span></h1>
      <div class="hero-subtitle">Daily Intelligence Dashboard</div>
      <p class="hero-desc">Five-pillar standing assessment tracking the United Kingdom&rsquo;s external positioning across defence, diplomacy, economics, trust, and soft power.</p>
      <div class="hero-date-nav">
        <a class="date-arrow{" disabled" if not prev_date_link else ""}" id="date-prev" title="Previous day">&larr;</a>
        <span class="date-label" id="hero-date">{display_date}</span>
        <a class="date-arrow disabled" id="date-next" title="Next day">&rarr;</a>
      </div>
    </div>
    <div class="score-block">
      <div class="score-block-inner">
        <div class="score-block-label">Composite Standing Score</div>
        <div class="score-block-num" id="composite-score">{composite}</div>
        <div class="score-block-max">of 100</div>
        <div class="score-block-delta {sb_delta_cls}">{sb_delta_content}</div>
        <div class="score-block-posture posture-{posture_cls}" id="composite-posture">{composite_posture}</div>
      </div>
    </div>
  </div>
  <div class="pillar-scores" id="pillar-scores">{pillar_score_cells}
  </div>
</div>

<div class="container">
  <div id="pillars">
    <div class="section-head">
      <h2 class="section-title">Pillar Assessments</h2>
      <span class="section-meta">Cycle: {display_date}</span>
    </div>
    <div class="pillar-tiles">{pillar_tiles_html}
    </div>
  </div>

  <div class="signals-strip" id="signals">
    <div class="section-head">
      <h2 class="section-title">Key Signals This Cycle</h2>
      <span class="section-meta">{signals_meta}</span>
    </div>
    <div class="signals-summary">{signals_html}
    </div>
  </div>

  <div class="trend-section">
    <div class="section-head">
      <h2 class="section-title">Standing History</h2>
      <span class="section-meta">Score Trend Over Time</span>
    </div>
    <div class="trend-note">
      {"Historical trend data will populate automatically as daily cycles accumulate. First cycle recorded: " + display_date + "." if len(dates) <= 1 else "Data available for " + str(len(dates)) + " cycles."}
    </div>
  </div>
</div>

<div class="footer">
  <div class="footer-inner">
    <div class="footer-left">
      <span class="footer-logo">NOAH</span>
      <span class="footer-label">Sovereign Signal</span>
    </div>
    <div class="footer-right">
      <div class="footer-text">Cycle: {display_date} &middot; &copy; Noah Wire Services 2026</div>
    </div>
  </div>
  <div class="footer-credit">
    Intelligence architecture by Noah Wire Services in partnership with Zinc Network &middot; Prepared for the Foreign, Commonwealth &amp; Development Office
  </div>
</div>

</body>
</html>'''


# ─── Per-Pillar Report Generation ─────────────────────────────────

def generate_pillar_report(key, pillar, pdata, target_date, report_link):
    """
    Generate a per-pillar HTML report page.
    For now, this embeds the RSS content in our design template.
    Later, the WF9 template will be used instead.
    """
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    display_date = dt.strftime("%d %B %Y")
    posture_cls = _posture_class(pdata.get("posture"))
    score = pdata.get("score", "—")
    exec_summary = pdata.get("executive_summary", "Assessment not available this cycle.")
    headline = f"{pillar['headline']} — {target_date}"

    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{headline}</title>
<meta property="og:title" content="{pillar['name']} — Sovereign Signal">
<meta property="og:description" content="UK {pillar['short']} standing intelligence — {display_date}">
<meta property="og:image" content="https://ivanmassow.github.io/client-reports/sovereign-signal/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{pillar['name']} — Sovereign Signal">
<meta name="twitter:image" content="https://ivanmassow.github.io/client-reports/sovereign-signal/og-image.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Lora:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root {{
  --slate: #1a1e27; --slate-deep: #1a1e27; --slate-mid: #2e323c;
  --accent: #C9A84C; --accent-light: #EDE0B8; --accent-muted: rgba(201,168,76,0.12);
  --red: #C4545A; --green: #3A8A6E; --amber: #C4920A;
  --text: #2C2C2C; --text-mid: #555B66; --text-muted: #8A8F98;
  --bg: #FAFAF8; --bg-card: #FFFFFF; --border: #E8E6E1; --border-light: #F2F0EB;
  --pillar: {pillar['color']}; --pillar-light: {pillar['color_light']}; --pillar-mid: {pillar['color_mid']};
  --card-radius: 8px; --card-shadow: 0 1px 3px rgba(0,0,0,0.04);
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; color: var(--text); background: var(--bg); -webkit-font-smoothing: antialiased; line-height: 1.6; }}
.topbar {{ background: var(--slate); display: flex; align-items: center; justify-content: space-between; padding: 0 32px; height: 52px; position: sticky; top: 0; z-index: 100; }}
.topbar-left {{ display: flex; align-items: center; gap: 14px; }}
.topbar-logo {{ font-family: 'Montserrat', sans-serif; font-weight: 700; font-size: 15px; letter-spacing: 0.06em; color: rgba(255,255,255,0.9); text-transform: uppercase; }}
.topbar-divider {{ width: 1px; height: 20px; background: rgba(255,255,255,0.12); }}
.topbar-brand {{ font-size: 11px; font-weight: 500; letter-spacing: 1.5px; text-transform: uppercase; color: rgba(255,255,255,0.45); }}
.topbar-right {{ display: flex; align-items: center; gap: 20px; }}
.topbar-date {{ font-size: 11px; color: rgba(255,255,255,0.35); }}
.back-link {{ font-size: 11px; font-weight: 500; color: rgba(255,255,255,0.45); text-decoration: none; padding: 6px 12px; border-radius: 4px; transition: all 0.15s; }}
.back-link:hover {{ color: #fff; background: rgba(255,255,255,0.08); }}
.hero {{ background: var(--slate-deep); position: relative; overflow: hidden; }}
.hero-bg {{ position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: url('union-flag.png') center center / cover no-repeat; opacity: 0.5; filter: saturate(0.6) contrast(1.05); }}
.hero::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: linear-gradient(105deg, rgba(26,30,39,0.97) 0%, rgba(26,30,39,0.93) 22%, rgba(26,30,39,0.72) 48%, rgba(26,30,39,0.35) 72%, rgba(26,30,39,0.18) 100%); z-index: 1; pointer-events: none; }}
.hero::after {{ content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 1px; background: rgba(255,255,255,0.08); z-index: 3; }}
.hero-inner {{ max-width: 1100px; margin: 0 auto; position: relative; z-index: 2; display: flex; align-items: flex-start; justify-content: space-between; padding: 56px 32px 52px; min-height: 280px; }}
.hero-left {{ flex: 1; padding-top: 8px; }}
.hero-tag {{ font-size: 9px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; padding: 3px 10px; border-radius: 4px; background: var(--pillar-light); color: var(--pillar); display: inline-block; margin-bottom: 14px; }}
.hero-title {{ font-family: 'Lora', Georgia, serif; font-size: 36px; font-weight: 700; color: white; line-height: 1.15; margin-bottom: 10px; }}
.hero-meta {{ font-size: 12px; color: rgba(255,255,255,0.35); letter-spacing: 1px; margin-bottom: 20px; }}
.hero-desc {{ font-family: 'Lora', Georgia, serif; font-size: 14px; color: rgba(255,255,255,0.38); max-width: 440px; line-height: 1.7; }}
.score-block {{ width: 220px; flex-shrink: 0; margin-top: 8px; }}
.score-block-inner {{ background: rgba(26,30,39,0.65); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 24px 20px 20px; text-align: center; }}
.score-block-label {{ font-size: 9px; font-weight: 600; letter-spacing: 2px; text-transform: uppercase; color: rgba(255,255,255,0.35); margin-bottom: 6px; }}
.score-block-num {{ font-family: 'Montserrat', sans-serif; font-size: 64px; font-weight: 800; color: white; line-height: 1; }}
.score-block-max {{ font-size: 11px; color: rgba(255,255,255,0.25); margin-top: 4px; margin-bottom: 12px; }}
.posture {{ display: inline-flex; align-items: center; gap: 6px; font-size: 10px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; padding: 4px 14px; border-radius: 4px; }}
.posture-mixed {{ color: var(--amber); background: rgba(196,146,10,0.12); }}
.posture-strong {{ color: var(--green); background: rgba(58,138,110,0.12); }}
.posture-weak {{ color: var(--red); background: rgba(196,84,90,0.12); }}
.main {{ max-width: 1100px; margin: 0 auto; padding: 0 32px; }}
.sec {{ margin-top: 48px; }}
.sec-head {{ padding-bottom: 14px; border-bottom: 1px solid var(--border); margin-bottom: 20px; display: flex; align-items: baseline; justify-content: space-between; }}
.sec-num {{ font-size: 11px; font-weight: 600; color: var(--pillar); letter-spacing: 1px; text-transform: uppercase; }}
.sec-title {{ font-family: 'Lora', Georgia, serif; font-size: 22px; font-weight: 600; color: var(--text); }}
.exec-card {{ background: var(--bg-card); border: 1px solid var(--border); border-left: 3px solid var(--pillar); padding: 24px 28px; border-radius: var(--card-radius); box-shadow: var(--card-shadow); }}
.exec-card p {{ font-family: 'Lora', Georgia, serif; font-size: 14px; color: var(--text-mid); line-height: 1.8; margin-bottom: 14px; }}
.source-link {{ display: inline-block; margin-top: 20px; padding: 10px 24px; background: var(--pillar); color: white; text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: 600; letter-spacing: 0.5px; transition: opacity 0.15s; }}
.source-link:hover {{ opacity: 0.85; }}
.footer {{ background: var(--slate-deep); padding: 28px 32px; margin-top: 48px; }}
.footer-inner {{ max-width: 1100px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; }}
.footer-left {{ display: flex; align-items: center; gap: 16px; }}
.footer-logo {{ font-family: 'Montserrat', sans-serif; font-weight: 700; font-size: 13px; letter-spacing: 0.06em; color: rgba(255,255,255,0.35); text-transform: uppercase; }}
.footer-label {{ font-size: 10px; font-weight: 400; color: rgba(255,255,255,0.2); }}
.footer-text {{ font-size: 10px; color: rgba(255,255,255,0.2); }}
.footer-credit {{ font-size: 9px; color: rgba(255,255,255,0.1); text-align: center; max-width: 1100px; margin: 12px auto 0; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.04); }}
@media (max-width: 900px) {{
  .hero-inner {{ flex-direction: column; padding: 36px 16px 36px; min-height: auto; }}
  .hero-title {{ font-size: 28px; }}
  .score-block {{ width: 100%; margin-top: 20px; }}
  .score-block-num {{ font-size: 48px; }}
  .topbar {{ padding: 0 16px; height: 48px; }}
  .main {{ padding: 0 16px; }}
}}
</style>
</head>
<body>
<div class="topbar">
  <div class="topbar-left">
    <div class="topbar-logo">NOAH</div>
    <div class="topbar-divider"></div>
    <span class="topbar-brand">Sovereign Signal</span>
  </div>
  <div class="topbar-right">
    <a class="back-link" href="index.html">&larr; Dashboard</a>
    <span class="topbar-date">{display_date}</span>
  </div>
</div>
<div class="hero">
  <div class="hero-bg"></div>
  <div class="hero-inner">
    <div class="hero-left">
      <span class="hero-tag">{pillar['short']}</span>
      <h1 class="hero-title">{pillar['name']}</h1>
      <div class="hero-meta">United Kingdom &mdash; {display_date}</div>
      <p class="hero-desc">{exec_summary[:200]}</p>
    </div>
    <div class="score-block">
      <div class="score-block-inner">
        <div class="score-block-label">Pillar Score</div>
        <div class="score-block-num">{score}</div>
        <div class="score-block-max">of 100</div>
        <div class="posture posture-{posture_cls}">{pdata.get('posture', 'Mixed')}</div>
      </div>
    </div>
  </div>
</div>
<div class="main">
  <div class="sec">
    <div class="sec-head">
      <h2 class="sec-title">Executive Summary</h2>
      <span class="sec-num">Section 01</span>
    </div>
    <div class="exec-card">
      <p>{exec_summary}</p>
    </div>
  </div>
  <div class="sec">
    <div class="sec-head">
      <h2 class="sec-title">Source Intelligence</h2>
      <span class="sec-num">Full Report</span>
    </div>
    <div class="exec-card">
      <p>The complete Sovereign Standing Brief for {pillar['name']} is available at the source link below. This includes the full Perception Dashboard, Trend Matrix, Signal Analysis, and Evidence Index.</p>
      <a class="source-link" href="{report_link}" target="_blank">View Full Source Report &rarr;</a>
    </div>
  </div>
</div>
<div class="footer">
  <div class="footer-inner">
    <div class="footer-left">
      <span class="footer-logo">NOAH</span>
      <span class="footer-label">Sovereign Signal</span>
    </div>
    <div class="footer-text">Cycle: {display_date} &middot; &copy; Noah Wire Services 2026</div>
  </div>
  <div class="footer-credit">Intelligence architecture by Noah Wire Services in partnership with Zinc Network &middot; Prepared for the Foreign, Commonwealth &amp; Development Office</div>
</div>
</body>
</html>"""

    filename = f"uk-{key}-{target_date}.html"
    output_path = SCRIPT_DIR / filename
    with open(output_path, "w") as f:
        f.write(report_html)
    print(f"  Pillar report written: {filename}")
    return filename


# ─── Main Orchestration ───────────────────────────────────────────

def run_once(target_date, require_all=True):
    """
    Poll the RSS feed once, parse reports for target_date.
    Returns True if all 5 pillars found (or require_all=False).
    """
    print(f"\n{'='*60}")
    print(f"  Sovereign Signal Poller — {target_date}")
    print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*60}\n")

    print("  Fetching RSS feed...")
    items = fetch_rss()
    print(f"  Found {len(items)} total items in feed")

    # Filter to target date
    day_items = filter_items_for_date(items, target_date)
    print(f"  Found {len(day_items)} items for {target_date}")

    # Classify each into pillars
    pillar_items = {}
    for item in day_items:
        pkey = classify_pillar(item["title"])
        if pkey:
            pillar_items[pkey] = item
            print(f"    {PILLARS[pkey]['short']:20s} -> {item['title'][:60]}...")
        else:
            print(f"    UNMATCHED          -> {item['title'][:60]}...")

    found = len(pillar_items)
    print(f"\n  Matched {found}/5 pillars")

    if require_all and found < 5:
        missing = [PILLARS[k]["short"] for k in PILLARS if k not in pillar_items]
        print(f"  Missing: {', '.join(missing)}")
        print("  Waiting for all 5 reports...")
        return False

    if found == 0:
        print("  No reports found for this date. Nothing to generate.")
        return False

    # Parse each report
    print("\n  Parsing report content...")
    pillar_data = {}
    for key, item in pillar_items.items():
        print(f"    Parsing {PILLARS[key]['short']}...")
        pdata = parse_report_content(item["description"])
        pdata["link"] = item["link"]
        pdata["ref"] = extract_ref_from_title(item["title"])
        pillar_data[key] = pdata
        print(f"      Score: {pdata.get('score', '?')}, Posture: {pdata.get('posture', '?')}, "
              f"Trends: {pdata['trend_count']}, Strengths: {pdata['strength_count']}, Vulns: {pdata['vuln_count']}")

    # Save data
    print("\n  Saving data...")
    history = save_day_data(target_date, pillar_data)

    # Generate per-pillar reports
    print("\n  Generating pillar reports...")
    for key, pdata in pillar_data.items():
        generate_pillar_report(key, PILLARS[key], pdata, target_date, pdata.get("link", ""))

    # Generate dashboard
    print("\n  Generating dashboard...")
    generate_dashboard(target_date, pillar_data, history)

    print(f"\n  Done! {found} reports processed.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Sovereign Signal RSS Poller")
    parser.add_argument("--date", help="Target date (YYYY-MM-DD)", default=None)
    parser.add_argument("--wait", action="store_true", help="Poll until all 5 reports arrive")
    parser.add_argument("--partial", action="store_true", help="Generate with whatever reports are available")
    args = parser.parse_args()

    target_date = args.date or datetime.utcnow().strftime("%Y-%m-%d")

    if args.wait:
        for attempt in range(MAX_POLLS):
            success = run_once(target_date, require_all=True)
            if success:
                break
            print(f"\n  Retry in {POLL_INTERVAL}s (attempt {attempt + 1}/{MAX_POLLS})...")
            time.sleep(POLL_INTERVAL)
        else:
            print("\n  Max polls reached. Generating with available reports...")
            run_once(target_date, require_all=False)
    elif args.partial:
        run_once(target_date, require_all=False)
    else:
        success = run_once(target_date, require_all=True)
        if not success:
            print("\n  Tip: Use --wait to poll until all 5 arrive, or --partial to generate with what's available.")


if __name__ == "__main__":
    main()
