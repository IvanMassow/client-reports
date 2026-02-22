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


def extract_arena_findings(exec_text, conclusion_text=""):
    """
    Extract individual arena-level findings from executive summary and conclusion.
    Returns list of dicts: {"arena": str, "posture": "Strong"|"Weak"|"Mixed"|"Uncertain", "detail": str}
    """
    findings = []
    seen = set()
    combined = (exec_text or "") + "\n" + (conclusion_text or "")

    # --- Strong arena patterns ---
    # "Strong structural positions in X, Y, and Z" — handle full comma-and lists
    for m in re.finditer(
        r'Strong\s+(?:structural\s+)?position(?:s|ing)?\s+in\s+([A-Z][A-Za-z,\s&]+?)(?:\s*(?:,\s*(?:but|while|alongside)|\.|\s+(?:Perception|This|Vulnerability|The)))',
        combined
    ):
        for arena in _split_arena_list(m.group(1)):
            if arena not in seen:
                seen.add(arena)
                findings.append({"arena": arena, "posture": "Strong", "detail": ""})

    # "X and Y present Strong positions"
    for m in re.finditer(
        r'([A-Z][A-Za-z,\s&]+?)\s+(?:present|remain(?:s)?)\s+(?:structurally\s+)?Strong\s+position',
        combined
    ):
        for arena in _split_arena_list(m.group(1)):
            if arena not in seen:
                seen.add(arena)
                findings.append({"arena": arena, "posture": "Strong", "detail": ""})

    # "structurally Strong in X"
    for m in re.finditer(
        r'structurally\s+Strong\s+in\s+([A-Z][A-Za-z,\s&]+?)(?:\s*(?:,\s*(?:while|but)|\.|\s+and\s+(?=[a-z])))',
        combined
    ):
        for arena in _split_arena_list(m.group(1)):
            if arena not in seen:
                seen.add(arena)
                findings.append({"arena": arena, "posture": "Strong", "detail": ""})

    # "X remain structurally Strong"
    for m in re.finditer(
        r'([A-Z][A-Za-z,\s&]+?)\s+remain(?:s)?\s+structurally\s+Strong',
        combined
    ):
        for arena in _split_arena_list(m.group(1)):
            if arena not in seen:
                seen.add(arena)
                findings.append({"arena": arena, "posture": "Strong", "detail": ""})

    # --- Weak arena patterns ---
    # "Weak structural positions in X, Y, and Z." — handle trailing comma-and list
    for m in re.finditer(
        r'Weak\s+(?:structural\s+)?position(?:s)?\s+in\s+([A-Z][A-Za-z,\s&]+?)(?:\s*(?:\.|\s+Perception|\s+This))',
        combined
    ):
        for arena in _split_arena_list(m.group(1)):
            if arena not in seen:
                seen.add(arena)
                findings.append({"arena": arena, "posture": "Weak", "detail": ""})

    # "X present Weak positions" or "is Weak"
    for m in re.finditer(
        r'([A-Z][A-Za-z\s&]+?)\s+(?:present|remain(?:s)?)\s+(?:structurally\s+)?Weak',
        combined
    ):
        for arena in _split_arena_list(m.group(1)):
            if arena not in seen:
                seen.add(arena)
                findings.append({"arena": arena, "posture": "Weak", "detail": ""})

    for m in re.finditer(
        r'([A-Z][A-Za-z\s&]+?)\s+is\s+(?:structurally\s+)?Weak',
        combined
    ):
        for arena in _split_arena_list(m.group(1)):
            if arena not in seen:
                seen.add(arena)
                findings.append({"arena": arena, "posture": "Weak", "detail": ""})

    # "while X is Weak" or "X are structurally Weak"
    for m in re.finditer(
        r'([A-Z][A-Za-z,\s&]+?)\s+(?:is|are)\s+(?:structurally\s+)?Weak',
        combined
    ):
        for arena in _split_arena_list(m.group(1)):
            if arena not in seen:
                seen.add(arena)
                findings.append({"arena": arena, "posture": "Weak", "detail": ""})

    # --- Mixed arena patterns ---
    # "while X remains Mixed" — require "while" or "but" prefix to avoid matching sentence subjects
    for m in re.finditer(
        r'(?:while|but|whereas)\s+([A-Z][A-Za-z\s&]+?)\s+(?:remains?|is)\s+Mixed',
        combined
    ):
        for arena in _split_arena_list(m.group(1)):
            if arena not in seen:
                seen.add(arena)
                findings.append({"arena": arena, "posture": "Mixed", "detail": ""})
    # "X remains Mixed due to"
    for m in re.finditer(
        r'([A-Z][A-Za-z\s&]+?)\s+(?:remains?|is)\s+Mixed\s+due\s+to',
        combined
    ):
        for arena in _split_arena_list(m.group(1)):
            if arena not in seen:
                seen.add(arena)
                findings.append({"arena": arena, "posture": "Mixed", "detail": ""})

    # --- Managed uncertainty / Insufficient data ---
    for m in re.finditer(
        r'([A-Z][A-Za-z\s&]+?)\s+remain(?:s)?\s+(?:in\s+)?(?:Managed\s+uncertainty|Insufficient\s+data|an?\s+explicit\s+silence)',
        combined
    ):
        for arena in _split_arena_list(m.group(1)):
            if arena not in seen:
                seen.add(arena)
                findings.append({"arena": arena, "posture": "Uncertain", "detail": "Insufficient data"})

    # --- Extract vulnerability detail from "Vulnerability concentrat..." sentences ---
    vuln_detail = re.search(
        r'Vulnerability\s+concentrat(?:es?|ion)\s+(?:is\s+)?(?:primarily\s+|highest\s+)?in\s+([A-Z][A-Za-z,\s&]+?)(?:\s+with\s+)',
        combined
    )
    if vuln_detail:
        for arena in _split_arena_list(vuln_detail.group(1)):
            # Update existing finding or add new
            found = False
            for f in findings:
                if f["arena"] == arena:
                    f["detail"] = "Vulnerability concentration"
                    found = True
                    break
            if not found and arena not in seen:
                seen.add(arena)
                findings.append({"arena": arena, "posture": "Weak", "detail": "Vulnerability concentration"})

    # --- Extract strength detail from "strength signals are concentrated in..." ---
    str_detail = re.search(
        r'strength\s+(?:signals?\s+(?:are\s+)?)?(?:most\s+)?(?:consistently\s+)?(?:concentrated|visible|present)\s+in\s+([A-Z][A-Za-z,\s&]+?)(?:\s*\()',
        combined
    )
    if str_detail:
        for arena in _split_arena_list(str_detail.group(1)):
            found = False
            for f in findings:
                if f["arena"] == arena:
                    f["detail"] = "Strength concentration"
                    found = True
                    break
            if not found and arena not in seen:
                seen.add(arena)
                findings.append({"arena": arena, "posture": "Strong", "detail": "Strength concentration"})

    return findings


def _split_arena_list(text):
    """Split a comma/and-separated arena string into individual arena names."""
    arenas = []
    # Split on " and " or ", " but not within arena names
    for part in re.split(r'\s+and\s+|\s*,\s+', text):
        p = part.strip().rstrip(',.')
        # Strip leading "and " left over from ", and " Oxford comma splits
        if p.lower().startswith("and "):
            p = p[4:].strip()
        # Filter out noise — must start uppercase, be >3 chars, not be common words
        noise_words = {
            "This", "The", "Strong", "Weak", "Mixed", "While", "Where",
            "Managed", "Multiple", "Vulnerability", "Several", "Each",
            "United", "United Kingdom", "Perception", "Standing", "Strong structural",
        }
        if (len(p) > 3 and p[0].isupper() and p not in noise_words
            and not p.startswith("United Kingdom")
            and not p.startswith("Multiple ")
            and "remain" not in p.lower()
            and "this cycle" not in p.lower()
            and "standing" not in p.lower()
            and "proposition" not in p.lower()
            and len(p.split()) <= 7):  # Arena names are typically 2-6 words
            arenas.append(p)
    return arenas


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
    prev_pillar_scores = {}
    if prev_date and prev_date in history:
        prev_scores = []
        for key in PILLARS:
            prev_s = history.get(prev_date, {}).get(key, {}).get("score")
            curr_s = pillar_data.get(key, {}).get("score")
            if prev_s is not None:
                prev_pillar_scores[key] = prev_s
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
        prev_pillar_scores=prev_pillar_scores,
        prev_composite=prev_composite,
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
                          composite_posture, pillar_data, deltas, dates,
                          prev_pillar_scores=None, prev_composite=None):
    """Build the full index.html dashboard from scratch using data."""

    posture_cls = _posture_class(composite_posture)
    composite_delta_html = _delta_html(composite_delta, is_hero=True)

    # Signal colour reflects composite posture
    posture_lower = (composite_posture or "").lower()
    if posture_lower == "strong":
        signal_color = "var(--green)"
    elif posture_lower in ("weak", "declining"):
        signal_color = "var(--red)"
    else:
        signal_color = "var(--amber)"

    # Build pillar score cells
    if prev_pillar_scores is None:
        prev_pillar_scores = {}
    pillar_score_cells = ""
    for key, pillar in PILLARS.items():
        pdata = pillar_data.get(key, {})
        score = pdata.get("score")
        score_display = score if score is not None else "—"
        post = pdata.get("posture") or "—"
        delta = deltas.get(key)
        delta_cls = "up" if delta and delta > 0 else "down" if delta and delta < 0 else "flat"
        cell_cls = "delta-up" if delta and delta > 0 else "delta-down" if delta and delta < 0 else ""

        # Previous score display — shows below current in its own colour
        prev_score = prev_pillar_scores.get(key)
        if prev_score is not None and delta is not None:
            # Previous score gets colour of what it was (green = positive direction at the time)
            prev_color = "var(--green)" if delta >= 0 else "var(--green)"  # prev was green when it was current
            prev_html = f'<div class="pillar-score-prev" style="color:{prev_color}">{prev_score}</div>'
        else:
            prev_html = '<div class="pillar-score-prev">&mdash;</div>'

        pillar_score_cells += f'''
      <a class="pillar-score-cell{" " + cell_cls if cell_cls else ""}" data-pillar="{key}" href="#tile-{key}">
        <div class="pillar-score-name">{pillar["name"]}</div>
        <div class="pillar-score-num">{score_display}</div>
        {prev_html}
        <div class="pillar-score-posture">{post}</div>
      </a>'''

    # Build briefing cards — one horizontal card per pillar with all findings
    briefing_cards_html = ""
    total_strengths = 0
    total_vulns = 0
    for key, pillar in PILLARS.items():
        pdata = pillar_data.get(key, {})
        score = pdata.get("score")
        score_display = score if score is not None else "—"
        post = pdata.get("posture") or "—"
        strength_count = pdata.get("strength_count", 0)
        vuln_count = pdata.get("vuln_count", 0)
        trend_count = pdata.get("trend_count", 0)
        total_strengths += strength_count
        total_vulns += vuln_count
        report_file = f"uk-{key}-{target_date}.html"
        href = report_file if (SCRIPT_DIR / report_file).exists() else "#"

        # Extract all arena-level findings
        exec_text = pdata.get("executive_summary", "")
        conclusion_text = pdata.get("conclusion", "")
        findings = extract_arena_findings(exec_text, conclusion_text)

        # Build finding rows — each arena gets its own row in the card
        findings_rows_html = ""
        if findings:
            for f in findings:
                posture = f["posture"]
                if posture == "Strong":
                    dot_cls = "finding-dot-strong"
                    badge_cls = "finding-badge-strong"
                elif posture == "Weak":
                    dot_cls = "finding-dot-weak"
                    badge_cls = "finding-badge-weak"
                elif posture == "Mixed":
                    dot_cls = "finding-dot-mixed"
                    badge_cls = "finding-badge-mixed"
                else:
                    dot_cls = "finding-dot-uncertain"
                    badge_cls = "finding-badge-uncertain"
                detail_span = ""
                if f["detail"]:
                    detail_span = f' <span class="finding-detail">{html.escape(f["detail"])}</span>'
                findings_rows_html += f'''
              <div class="finding-row">
                <span class="finding-dot {dot_cls}"></span>
                <span class="finding-arena">{html.escape(f["arena"])}</span>
                <span class="finding-badge {badge_cls}">{posture}</span>{detail_span}
              </div>'''
        else:
            # Fallback — show signal counts
            findings_rows_html = '<div class="finding-row finding-row-fallback">'
            if strength_count:
                findings_rows_html += f'<span class="finding-tag strength">{strength_count} strengths</span>'
            if vuln_count:
                findings_rows_html += f'<span class="finding-tag vuln">{vuln_count} vulnerabilities</span>'
            if trend_count:
                findings_rows_html += f'<span class="finding-tag">{trend_count} trends</span>'
            findings_rows_html += '</div>'

        briefing_cards_html += f'''
      <a class="briefing-card" data-pillar="{key}" id="tile-{key}" href="{href}">
        <div class="briefing-card-top">
          <div class="briefing-card-left">
            <span class="briefing-card-tag">{pillar["short"]}</span>
            <span class="briefing-card-title">{pillar["name"]}</span>
          </div>
          <div class="briefing-card-stats">
            <div class="briefing-card-score">{score_display}</div>
            <div class="briefing-card-meta">
              <div class="briefing-card-meta-val" style="color:var(--green)">{strength_count}</div>
              <div class="briefing-card-meta-label">Strengths</div>
            </div>
            <div class="briefing-card-meta">
              <div class="briefing-card-meta-val" style="color:var(--red)">{vuln_count}</div>
              <div class="briefing-card-meta-label">Vulns</div>
            </div>
            <div class="briefing-card-meta">
              <div class="briefing-card-meta-val">{trend_count}</div>
              <div class="briefing-card-meta-label">Trends</div>
            </div>
          </div>
        </div>
        <div class="briefing-card-findings-grid">{findings_rows_html}
        </div>
        <div class="briefing-card-cta">View Full Report &rarr;</div>
      </a>'''

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
        sb_delta_content = f'&#9650; +{composite_delta} <span style="color:var(--green);opacity:0.6">was {prev_composite}</span>'
    elif composite_delta < 0:
        sb_delta_cls = "down"
        sb_delta_content = f'&#9660; {composite_delta} <span style="color:var(--green);opacity:0.6">was {prev_composite}</span>'
    else:
        sb_delta_cls = "flat"
        sb_delta_content = f'&mdash; <span style="opacity:0.6">was {prev_composite}</span>'

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
      <h1 class="hero-title">Sovereign<br><span style="color:{signal_color}">Signal</span></h1>
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
      <h2 class="section-title">Pillar Briefings</h2>
      <span class="section-meta">Cycle: {display_date} &middot; {total_strengths} strengths &middot; {total_vulns} vulnerabilities</span>
    </div>
    <div class="briefing-cards">{briefing_cards_html}
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
    Generate a full editorial per-pillar HTML report page.
    Renders all parsed intelligence data in a structured, beautiful layout.
    No prominent links to raw source — source template link at very bottom only.
    """
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    display_date = dt.strftime("%d %B %Y")
    posture_cls = _posture_class(pdata.get("posture"))
    score = pdata.get("score", "—")
    posture = pdata.get("posture", "Mixed")
    exec_summary = pdata.get("executive_summary", "")
    conclusion = pdata.get("conclusion", "")
    strength_count = pdata.get("strength_count", 0)
    vuln_count = pdata.get("vuln_count", 0)
    trend_count = pdata.get("trend_count", 0)
    ref_code = pdata.get("ref", "")
    headline = f"{pillar['name']} — Sovereign Signal"

    # Handle missing executive summary
    if not exec_summary or exec_summary.startswith("[Section"):
        exec_summary = "Assessment data not available for this cycle. The intelligence pipeline did not return a structured executive summary for this pillar."

    # Split executive summary into paragraphs
    exec_paragraphs = [p.strip() for p in exec_summary.split("\n") if p.strip()]
    exec_html = ""
    for i, para in enumerate(exec_paragraphs):
        weight = ' style="font-weight:600"' if i == 0 else ""
        exec_html += f"      <p{weight}>{html.escape(para)}</p>\n"

    # Extract arena findings
    findings = extract_arena_findings(exec_summary, conclusion)

    # Build arena scorecard — grid of arena cards with posture badges
    arena_cards_html = ""
    strong_count = sum(1 for f in findings if f["posture"] == "Strong")
    weak_count = sum(1 for f in findings if f["posture"] == "Weak")
    mixed_count = sum(1 for f in findings if f["posture"] == "Mixed")
    uncertain_count = sum(1 for f in findings if f["posture"] == "Uncertain")

    for f in findings:
        p = f["posture"]
        if p == "Strong":
            border_color = "var(--green)"
            badge_bg = "rgba(58,138,110,0.1)"
            badge_color = "#166534"
        elif p == "Weak":
            border_color = "var(--red)"
            badge_bg = "rgba(196,84,90,0.1)"
            badge_color = "#991b1b"
        elif p == "Mixed":
            border_color = "var(--amber)"
            badge_bg = "rgba(196,146,10,0.1)"
            badge_color = "#92400e"
        else:
            border_color = "var(--text-muted)"
            badge_bg = "var(--bg)"
            badge_color = "var(--text-muted)"

        detail_html = ""
        if f["detail"]:
            detail_html = f'<div class="arena-card-detail">{html.escape(f["detail"])}</div>'

        arena_cards_html += f'''
        <div class="arena-card" style="border-left:4px solid {border_color}">
          <div class="arena-card-name">{html.escape(f["arena"])}</div>
          <span class="arena-badge" style="background:{badge_bg};color:{badge_color}">{p.upper()}</span>
          {detail_html}
        </div>'''

    # Build key statistics row
    stats_html = f'''
      <div class="key-stats">
        <div class="key-stat">
          <div class="key-stat-num" style="color:var(--pillar)">{len(findings)}</div>
          <div class="key-stat-label">Arenas Assessed</div>
        </div>
        <div class="key-stat">
          <div class="key-stat-num" style="color:var(--green)">{strong_count}</div>
          <div class="key-stat-label">Arenas Strong</div>
        </div>
        <div class="key-stat">
          <div class="key-stat-num" style="color:var(--red)">{weak_count}</div>
          <div class="key-stat-label">Arenas Weak</div>
        </div>
        <div class="key-stat">
          <div class="key-stat-num" style="color:var(--green)">{strength_count}</div>
          <div class="key-stat-label">Strength Signals</div>
        </div>
        <div class="key-stat">
          <div class="key-stat-num" style="color:var(--red)">{vuln_count}</div>
          <div class="key-stat-label">Vulnerability Signals</div>
        </div>
        <div class="key-stat">
          <div class="key-stat-num">{trend_count}</div>
          <div class="key-stat-label">Trends Tracked</div>
        </div>
      </div>'''

    # Build strength signals section
    strength_ids = pdata.get("strength_signals", [])
    # Deduplicate while preserving order
    seen_ss = set()
    unique_ss = []
    for s in strength_ids:
        if s not in seen_ss:
            seen_ss.add(s)
            unique_ss.append(s)

    strength_table = ""
    if unique_ss:
        rows = ""
        for s in unique_ss:
            rows += f'        <tr><td class="signal-id signal-id-strong">{s}</td><td>Structural strength signal identified in the external assessment set</td></tr>\n'
        strength_table = f'''
      <table class="signal-table">
        <thead><tr><th>Signal ID</th><th>Assessment</th></tr></thead>
        <tbody>
{rows}        </tbody>
      </table>'''

    # Build vulnerability signals section
    vuln_ids = pdata.get("vulnerability_signals", [])
    seen_vs = set()
    unique_vs = []
    for v in vuln_ids:
        if v not in seen_vs:
            seen_vs.add(v)
            unique_vs.append(v)

    vuln_table = ""
    if unique_vs:
        rows = ""
        for v in unique_vs:
            rows += f'        <tr><td class="signal-id signal-id-vuln">{v}</td><td>Vulnerability signal identified in the external assessment set</td></tr>\n'
        vuln_table = f'''
      <table class="signal-table">
        <thead><tr><th>Signal ID</th><th>Assessment</th></tr></thead>
        <tbody>
{rows}        </tbody>
      </table>'''

    # Build conclusion
    conclusion_html = ""
    if conclusion and not conclusion.startswith("[Section"):
        conclusion_paras = [p.strip() for p in conclusion.split("\n") if p.strip()]
        for para in conclusion_paras:
            conclusion_html += f"      <p>{html.escape(para)}</p>\n"
    else:
        conclusion_html = "      <p>Standing assessment data will populate when available.</p>\n"

    # Source link — raw template reference at the very bottom
    source_section = ""
    if report_link:
        source_section = f'''
  <div class="source-section">
    <div class="source-inner">
      <div class="source-label">SOURCES &amp; RAW TEMPLATE</div>
      <p class="source-text">This report was generated from the Sovereign Standing Brief intelligence template produced by the Noah analytical pipeline. The raw template used to generate this report is available below.</p>
      <a class="source-link-quiet" href="{report_link}" target="_blank" rel="noopener">View Raw Intelligence Template &rarr;</a>
    </div>
  </div>'''

    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{headline}</title>
<meta property="og:title" content="{html.escape(headline)}">
<meta property="og:description" content="UK {pillar['short']} standing intelligence &mdash; {display_date}">
<meta property="og:image" content="https://ivanmassow.github.io/client-reports/sovereign-signal/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{html.escape(headline)}">
<meta name="twitter:image" content="https://ivanmassow.github.io/client-reports/sovereign-signal/og-image.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Lora:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root {{
  --slate: #1a1e27; --slate-deep: #1a1e27; --slate-mid: #2e323c;
  --accent: #C9A84C; --accent-light: #EDE0B8;
  --red: #C4545A; --green: #3A8A6E; --amber: #C4920A;
  --text: #2C2C2C; --text-mid: #555B66; --text-muted: #8A8F98;
  --bg: #FAFAF8; --bg-card: #FFFFFF; --border: #E8E6E1; --border-light: #F2F0EB;
  --pillar: {pillar['color']}; --pillar-light: {pillar['color_light']}; --pillar-mid: {pillar['color_mid']};
  --card-radius: 8px; --card-shadow: 0 1px 3px rgba(0,0,0,0.04);
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; color: var(--text); background: var(--bg); -webkit-font-smoothing: antialiased; line-height: 1.6; }}

/* Topbar */
.topbar {{ background: var(--slate); display: flex; align-items: center; justify-content: space-between; padding: 0 32px; height: 52px; position: sticky; top: 0; z-index: 100; }}
.topbar-left {{ display: flex; align-items: center; gap: 14px; }}
.topbar-logo {{ font-family: 'Montserrat', sans-serif; font-weight: 700; font-size: 15px; letter-spacing: 0.06em; color: rgba(255,255,255,0.9); text-transform: uppercase; }}
.topbar-divider {{ width: 1px; height: 20px; background: rgba(255,255,255,0.12); }}
.topbar-brand {{ font-size: 11px; font-weight: 500; letter-spacing: 1.5px; text-transform: uppercase; color: rgba(255,255,255,0.45); }}
.topbar-right {{ display: flex; align-items: center; gap: 20px; }}
.topbar-date {{ font-size: 11px; color: rgba(255,255,255,0.35); }}
.back-link {{ font-size: 11px; font-weight: 500; color: rgba(255,255,255,0.45); text-decoration: none; padding: 6px 12px; border-radius: 4px; transition: all 0.15s; }}
.back-link:hover {{ color: #fff; background: rgba(255,255,255,0.08); }}

/* Hero */
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

/* Main Content */
.main {{ max-width: 1100px; margin: 0 auto; padding: 0 32px; }}
.sec {{ margin-top: 48px; }}
.sec-head {{ padding-bottom: 14px; border-bottom: 1px solid var(--border); margin-bottom: 20px; display: flex; align-items: baseline; justify-content: space-between; }}
.sec-num {{ font-size: 11px; font-weight: 600; color: var(--pillar); letter-spacing: 1px; text-transform: uppercase; }}
.sec-title {{ font-family: 'Lora', Georgia, serif; font-size: 22px; font-weight: 600; color: var(--text); }}
.exec-card {{ background: var(--bg-card); border: 1px solid var(--border); border-left: 4px solid var(--pillar); padding: 28px 32px; border-radius: var(--card-radius); box-shadow: var(--card-shadow); }}
.exec-card p {{ font-family: 'Lora', Georgia, serif; font-size: 14px; color: var(--text-mid); line-height: 1.8; margin-bottom: 14px; }}
.exec-card p:last-child {{ margin-bottom: 0; }}

/* Key Statistics */
.key-stats {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 1px; background: var(--border-light); border: 1px solid var(--border); border-radius: var(--card-radius); overflow: hidden; margin-top: 28px; }}
.key-stat {{ background: var(--bg-card); padding: 20px 12px; text-align: center; }}
.key-stat-num {{ font-family: 'Montserrat', sans-serif; font-size: 32px; font-weight: 800; line-height: 1; margin-bottom: 6px; color: var(--text); }}
.key-stat-label {{ font-size: 9px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; color: var(--text-muted); }}

/* Arena Cards */
.arena-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }}
.arena-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--card-radius); padding: 16px 20px; box-shadow: var(--card-shadow); display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
.arena-card-name {{ font-size: 14px; font-weight: 600; color: var(--text); flex: 1; }}
.arena-badge {{ font-size: 9px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; padding: 3px 10px; border-radius: 10px; flex-shrink: 0; }}
.arena-card-detail {{ font-size: 10px; color: var(--text-muted); width: 100%; margin-top: -4px; }}

/* Signal Tables */
.signal-table {{ width: 100%; border-collapse: collapse; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--card-radius); overflow: hidden; box-shadow: var(--card-shadow); }}
.signal-table thead th {{ font-size: 10px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; color: var(--text-muted); padding: 12px 16px; text-align: left; border-bottom: 2px solid var(--border); background: var(--bg); }}
.signal-table tbody td {{ font-size: 13px; color: var(--text-mid); padding: 10px 16px; border-bottom: 1px solid var(--border-light); }}
.signal-table tbody tr:last-child td {{ border-bottom: none; }}
.signal-id {{ font-family: 'Montserrat', sans-serif; font-weight: 700; font-size: 12px; letter-spacing: 0.5px; white-space: nowrap; }}
.signal-id-strong {{ color: var(--green); }}
.signal-id-vuln {{ color: var(--red); }}

/* Conclusion card */
.conclusion-card {{ background: var(--bg-card); border: 1px solid var(--border); border-left: 4px solid var(--pillar); padding: 28px 32px; border-radius: var(--card-radius); box-shadow: var(--card-shadow); }}
.conclusion-card p {{ font-family: 'Lora', Georgia, serif; font-size: 14px; color: var(--text-mid); line-height: 1.8; margin-bottom: 14px; }}
.conclusion-card p:last-child {{ margin-bottom: 0; }}
.conclusion-posture {{ display: inline-flex; align-items: center; gap: 8px; margin-top: 16px; font-size: 12px; font-weight: 600; }}
.conclusion-posture-badge {{ font-size: 10px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; padding: 4px 14px; border-radius: 4px; }}

/* Source section — quiet, at the very bottom */
.source-section {{ background: var(--bg); border-top: 1px solid var(--border); padding: 28px 32px; margin-top: 48px; }}
.source-inner {{ max-width: 1100px; margin: 0 auto; }}
.source-label {{ font-size: 9px; font-weight: 600; letter-spacing: 1.5px; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px; }}
.source-text {{ font-size: 12px; color: var(--text-muted); line-height: 1.6; margin-bottom: 12px; }}
.source-link-quiet {{ font-size: 11px; font-weight: 600; color: var(--pillar); text-decoration: none; opacity: 0.7; transition: opacity 0.15s; }}
.source-link-quiet:hover {{ opacity: 1; }}

/* Footer */
.footer {{ background: var(--slate-deep); padding: 28px 32px; margin-top: 0; }}
.footer-inner {{ max-width: 1100px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; }}
.footer-left {{ display: flex; align-items: center; gap: 16px; }}
.footer-logo {{ font-family: 'Montserrat', sans-serif; font-weight: 700; font-size: 13px; letter-spacing: 0.06em; color: rgba(255,255,255,0.35); text-transform: uppercase; }}
.footer-label {{ font-size: 10px; font-weight: 400; color: rgba(255,255,255,0.2); }}
.footer-text {{ font-size: 10px; color: rgba(255,255,255,0.2); }}
.footer-credit {{ font-size: 9px; color: rgba(255,255,255,0.1); text-align: center; max-width: 1100px; margin: 12px auto 0; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.04); }}

/* Responsive */
@media (max-width: 900px) {{
  .hero-inner {{ flex-direction: column; padding: 36px 16px 36px; min-height: auto; }}
  .hero-title {{ font-size: 28px; }}
  .score-block {{ width: 100%; margin-top: 20px; }}
  .score-block-inner {{ display: flex; align-items: center; gap: 16px; padding: 16px 20px; text-align: left; }}
  .score-block-label {{ display: none; }}
  .score-block-num {{ font-size: 48px; }}
  .score-block-max {{ display: none; }}
  .topbar {{ padding: 0 16px; height: 48px; }}
  .main {{ padding: 0 16px; }}
  .key-stats {{ grid-template-columns: repeat(3, 1fr); }}
  .key-stat-num {{ font-size: 24px; }}
  .arena-grid {{ grid-template-columns: 1fr; }}
  .exec-card {{ padding: 20px; }}
  .conclusion-card {{ padding: 20px; }}
  .source-section {{ padding: 20px 16px; }}
  .footer {{ padding: 20px 16px; }}
  .footer-inner {{ flex-direction: column; gap: 8px; text-align: center; }}
}}
@media (max-width: 600px) {{
  .hero-inner {{ padding: 24px 16px 28px; }}
  .hero-title {{ font-size: 24px; }}
  .hero-desc {{ display: none; }}
  .key-stats {{ grid-template-columns: repeat(2, 1fr); }}
  .key-stat-num {{ font-size: 22px; }}
  .key-stat {{ padding: 14px 8px; }}
  .signal-table {{ font-size: 12px; }}
  .signal-table thead th {{ padding: 8px 12px; }}
  .signal-table tbody td {{ padding: 8px 12px; }}
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
      <div class="hero-meta">United Kingdom &mdash; {display_date} &middot; Ref: {ref_code}</div>
      <p class="hero-desc">{html.escape(exec_summary[:200])}</p>
    </div>
    <div class="score-block">
      <div class="score-block-inner">
        <div class="score-block-label">Pillar Score</div>
        <div class="score-block-num">{score}</div>
        <div class="score-block-max">of 100</div>
        <div class="posture posture-{posture_cls}">{posture}</div>
      </div>
    </div>
  </div>
</div>

<div class="main">

  <!-- Section 01: Executive Summary -->
  <div class="sec">
    <div class="sec-head">
      <h2 class="sec-title">Executive Summary</h2>
      <span class="sec-num">Section 01</span>
    </div>
    <div class="exec-card">
{exec_html}    </div>
  </div>

  <!-- Key Statistics -->
  {stats_html}

  <!-- Section 02: Arena Scorecard -->
  <div class="sec">
    <div class="sec-head">
      <h2 class="sec-title">Arena Scorecard</h2>
      <span class="sec-num">Section 02</span>
    </div>
    <div class="arena-grid">{arena_cards_html}
    </div>
  </div>

  <!-- Section 03: Strength Signals -->
  <div class="sec">
    <div class="sec-head">
      <h2 class="sec-title">Sovereign Strength Signals</h2>
      <span class="sec-num">Section 03 &middot; {len(unique_ss)} signals</span>
    </div>
    {strength_table if strength_table else '<div class="exec-card"><p>No strength signals recorded this cycle.</p></div>'}
  </div>

  <!-- Section 04: Vulnerability Signals -->
  <div class="sec">
    <div class="sec-head">
      <h2 class="sec-title">Sovereign Vulnerability Signals</h2>
      <span class="sec-num">Section 04 &middot; {len(unique_vs)} signals</span>
    </div>
    {vuln_table if vuln_table else '<div class="exec-card"><p>No vulnerability signals recorded this cycle.</p></div>'}
  </div>

  <!-- Section 05: Standing Assessment -->
  <div class="sec">
    <div class="sec-head">
      <h2 class="sec-title">Standing Assessment</h2>
      <span class="sec-num">Conclusion</span>
    </div>
    <div class="conclusion-card">
{conclusion_html}      <div class="conclusion-posture">
        Standing posture this cycle: <span class="conclusion-posture-badge posture-{posture_cls}">{posture}</span>
      </div>
    </div>
  </div>

</div>

{source_section}

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
