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
        "gold_word": "Cultural",
        "pillar_num": "P1",
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
        "gold_word": "Strategic",
        "pillar_num": "P2",
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
        "gold_word": "Leadership",
        "pillar_num": "P3",
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
        "gold_word": "Global",
        "pillar_num": "P4",
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
        "gold_word": "Stability",
        "pillar_num": "P5",
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


PILLAR_ARENA_KEYWORDS = {
    "softpower": ["heritage identity", "cultural standing", "sporting brand", "creative industries", "culture and media", "education and research"],
    "defence": ["military capability", "nuclear deterrent", "nato positioning", "arms export", "defence industrial"],
    "economic": ["trade competitiveness", "innovation and technology", "financial services", "fiscal credibility", "investment"],
    "diplomatic": ["multilateral influence", "crisis diplomacy", "climate and energy", "sanctions and statecraft", "global voice"],
    "trust": ["governance stability", "regulatory competence", "media independence", "judicial authority", "partner reliability"],
}

def classify_pillar(title, desc=""):
    """Match an RSS item title to one of our 5 pillars.
    Uses best-match scoring (most keyword hits wins) to avoid false positives
    from overlapping keywords. Falls back to description arena names."""
    title_lower = title.lower()
    # Score each pillar by number of keyword matches in title — most wins
    scores = {}
    for key, pillar in PILLARS.items():
        count = sum(1 for kw in pillar["keywords"] if kw in title_lower)
        if count > 0:
            scores[key] = count
    if scores:
        return max(scores, key=scores.get)
    # Fallback: check description for arena-specific keywords
    if desc:
        desc_lower = desc.lower()
        for key, arenas in PILLAR_ARENA_KEYWORDS.items():
            matches = sum(1 for a in arenas if a in desc_lower)
            if matches >= 2:
                return key
    return None


def filter_items_for_date(items, target_date):
    """Filter RSS items to those matching the target date string."""
    return [i for i in items if extract_date_from_title(i["title"]) == target_date]


# ─── Content Parsing ──────────────────────────────────────────────

def _fix_emdashes(text):
    """Fix upstream LLM ` , ` substitution for em-dashes in prose text.
    Replaces ' , ' with ' — ' in mid-sentence contexts (not table cells or lists)."""
    # Pattern: word/punctuation/closing-bracket, space-comma-space, word
    # This avoids hitting table pipe fields or legitimate comma usage
    return re.sub(r'(?<=[\w\)\]\.\?!])\s,\s(?=[A-Za-z0-9])', ' \u2014 ', text)


def _strip_tags(html_text):
    """Strip HTML tags, returning plain text. Also fixes em-dash encoding."""
    text = re.sub(r"<[^>]+>", "", html_text).strip()
    return _fix_emdashes(text)


def _extract_li_field(li_html, field_name):
    """Extract a named field from a <li> item like '<strong>Arena:</strong> Foo'"""
    m = re.search(
        r"<strong>" + re.escape(field_name) + r"[:\s]*</strong>\s*(.*?)(?:</li>|$)",
        li_html, re.DOTALL | re.IGNORECASE
    )
    if m:
        return _strip_tags(m.group(1)).strip().rstrip(",")
    return ""


def parse_report_content(desc_html):
    """
    Parse the HTML description from the RSS feed to extract ALL structured data:
    - Executive summary
    - Sovereign Perception Dashboard (propositions + scores)
    - Trend Matrix (per-trend rows)
    - Arena Context (per-arena metadata: momentum, temperature, geographies)
    - Strength signals (full cards with title, arena, character, horizon, description)
    - Vulnerability signals (full cards with title, arena, severity, horizon, description)
    - Strategic Attention Priorities
    - Standing Assessment Overview (4-dimension summary)
    - Standing assessment / conclusion
    """
    data = {
        "executive_summary": "",
        "perception_dashboard": [],
        "trends": [],
        "arena_context": {},
        "strength_signals": [],
        "strength_signal_details": [],
        "vulnerability_signals": [],
        "vuln_signal_details": [],
        "priorities": [],
        "standing_overview": [],
        "conclusion": "",
        "score": None,
        "posture": None,
        "trend_count": 0,
        "strength_count": 0,
        "vuln_count": 0,
        "predictions": [],
        "arena_predictions": {},
        "exec_what": "",
        "exec_why": "",
        "exec_watch": "",
        "profile_snapshot": {},
        "structural_contradictions": "",
        "diagnostic_coverage": [],
    }

    # ─── Executive Summary ───
    exec_match = re.search(
        r"<h2[^>]*>.*?Executive Summary.*?</h2>(.*?)(?=<h2|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if exec_match:
        exec_block = exec_match.group(1)
        data["executive_summary"] = _strip_tags(exec_block)

        # Try to parse v2.2 "What is happening / Why it matters / What to watch" sub-blocks
        what_match = re.search(
            r"(?:<h3[^>]*>)?.*?What is happening.*?(?:</h3>)?\s*(.*?)(?=<h3|<h2|$)",
            exec_block, re.DOTALL | re.IGNORECASE
        )
        why_match = re.search(
            r"(?:<h3[^>]*>)?.*?Why it matters.*?(?:</h3>)?\s*(.*?)(?=<h3|<h2|$)",
            exec_block, re.DOTALL | re.IGNORECASE
        )
        watch_match = re.search(
            r"(?:<h3[^>]*>)?.*?What to watch.*?(?:</h3>)?\s*(.*?)(?=<h3|<h2|$)",
            exec_block, re.DOTALL | re.IGNORECASE
        )
        if what_match or why_match or watch_match:
            data["exec_what"] = _strip_tags(what_match.group(1)).strip() if what_match else ""
            data["exec_why"] = _strip_tags(why_match.group(1)).strip() if why_match else ""
            data["exec_watch"] = _strip_tags(watch_match.group(1)).strip() if watch_match else ""

    # ─── Perception Dashboard ───
    dashboard_section = re.search(
        r"Sovereign Perception Dashboard.*?</h2>(.*?)(?=<h2|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if dashboard_section:
        section_text = _strip_tags(dashboard_section.group(1))
        # Detect table format from header row
        header_row = ""
        for row in section_text.split("\n"):
            row = row.strip()
            if row.startswith("|") and ("Proposition" in row or "Arena" in row):
                header_row = row
                break
        has_sovereign_col = "Sovereign" in header_row or "Global" in header_row
        # v2.2 arena-grouped format: Arena | External Perception | Signal Strength | Detail | Emerging
        is_arena_grouped = "Arena" in header_row and "Detail" in header_row

        current_arena = ""
        for row in section_text.split("\n"):
            row = row.strip()
            if not row.startswith("|") or row.startswith("|---"):
                continue
            # Skip header rows
            if "Proposition" in row or ("Arena" in row and "External" in row):
                continue
            cols = [c.strip() for c in row.split("|")]
            cols = [c for c in cols if c]

            if is_arena_grouped and len(cols) >= 3:
                # v2.2 arena-grouped format
                # Arena summary rows are bold: **Arena Name** | **XX%** | **Strong** | | , |
                # Proposition rows have └ prefix: └ Prop text | XX% | Strong | Detail | , |
                raw_name = cols[0]
                is_arena_row = "**" in raw_name or (not raw_name.startswith("└") and not raw_name.startswith("&lfloor;"))
                clean_name = raw_name.replace("**", "").replace("└", "").strip()

                pct_str = cols[1].replace("**", "").replace("%", "").strip() if len(cols) > 1 else ""
                signal = cols[2].replace("**", "").strip() if len(cols) > 2 else ""
                detail = cols[3].strip() if len(cols) > 3 else ""
                emerging = cols[4].strip() if len(cols) > 4 else ""

                try:
                    pct = int(pct_str)
                except ValueError:
                    pct = None

                if is_arena_row:
                    current_arena = clean_name
                    # Arena summary row — store with arena as both proposition and arena
                    data["perception_dashboard"].append({
                        "proposition": clean_name,
                        "global_view": pct,
                        "sovereign_view": None,
                        "signal_strength": signal,
                        "arena": clean_name,
                        "emerging": emerging.strip(", "),
                        "is_arena_summary": True,
                    })
                else:
                    # Proposition detail row
                    data["perception_dashboard"].append({
                        "proposition": clean_name,
                        "global_view": pct,
                        "sovereign_view": None,
                        "signal_strength": signal,
                        "arena": current_arena,
                        "emerging": emerging.strip(", "),
                        "is_arena_summary": False,
                    })

            elif has_sovereign_col and len(cols) >= 6:
                # Old format: Proposition | Global View | Sovereign View | Signal | Arena | Emerging
                prop_text = cols[0]
                global_view = cols[1].replace("%", "").strip()
                sovereign_view = cols[2].replace("%", "").strip()
                signal_strength = cols[3].strip()
                arena = cols[4].strip()
                emerging = cols[5] if len(cols) > 5 else ""
                try:
                    gv = int(global_view)
                except ValueError:
                    gv = None
                try:
                    sv = int(sovereign_view)
                except ValueError:
                    sv = None
                data["perception_dashboard"].append({
                    "proposition": prop_text,
                    "global_view": gv,
                    "sovereign_view": sv,
                    "signal_strength": signal_strength,
                    "arena": arena,
                    "emerging": emerging.strip(", "),
                })

            elif len(cols) >= 4:
                # Earlier v2.2: Proposition | External Perception | Signal | Arena | Emerging
                prop_text = cols[0]
                global_view = cols[1].replace("%", "").strip()
                sovereign_view = ""
                signal_strength = cols[2].strip()
                arena = cols[3].strip()
                emerging = cols[4] if len(cols) > 4 else ""
                try:
                    gv = int(global_view)
                except ValueError:
                    gv = None
                try:
                    sv = int(sovereign_view)
                except ValueError:
                    sv = None
                data["perception_dashboard"].append({
                    "proposition": prop_text,
                    "global_view": gv,
                    "sovereign_view": sv,
                    "signal_strength": signal_strength,
                    "arena": arena,
                    "emerging": emerging.strip(", "),
                })

    # ─── Trend Matrix ───
    trend_section = re.search(
        r"Trend Matrix.*?</h2>(.*?)(?=<h2|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if trend_section:
        section_text = _strip_tags(trend_section.group(1))
        for row in section_text.split("\n"):
            row = row.strip()
            if not row.startswith("|") or row.startswith("|---") or "Trend" in row and "Arena" in row:
                continue
            cols = [c.strip() for c in row.split("|")]
            cols = [c for c in cols if c]
            if len(cols) >= 6 and re.match(r"TRU-T\d+", cols[0]):
                trend_id = cols[0].split("(")[0].strip()
                arena_slug = cols[1].strip()
                signal_type = cols[2].strip()
                spot_check = cols[3].strip()
                relevance = cols[4].strip() if len(cols) > 4 else ""
                momentum = cols[5].strip() if len(cols) > 5 else ""
                temperature = cols[6].strip() if len(cols) > 6 else ""

                # Convert arena slug to title case
                arena_name = arena_slug.replace("_", " ").title()

                data["trends"].append({
                    "id": trend_id,
                    "arena": arena_name,
                    "signal_type": signal_type,
                    "spot_check": spot_check,
                    "relevance": relevance,
                    "momentum": momentum,
                    "temperature": temperature,
                })

    data["trend_count"] = len(data["trends"])

    # ─── Arena Context (Sovereign Standing Context) ───
    arena_section = re.search(
        r"Sovereign Standing Context.*?</h2>(.*?)(?=<h2[^3-9]|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if arena_section:
        arena_html = arena_section.group(1)
        # Split by h4 tags for each arena
        arena_blocks = re.split(r"<h4>([^<]+)</h4>", arena_html)
        # arena_blocks: [pre-content, name1, content1, name2, content2, ...]
        for i in range(1, len(arena_blocks), 2):
            arena_name = arena_blocks[i].strip()
            block_html = arena_blocks[i + 1] if i + 1 < len(arena_blocks) else ""
            block_text = _strip_tags(block_html)

            ctx = {"name": arena_name}
            # Extract structured fields — support both old and v2.2 field names
            for fields, key in [
                (["Verified trend count", "Active trends"], "spot_checked_trends"),
                (["Dominant momentum"], "momentum"),
                (["Geographic concentration"], "geo_concentration"),
                (["Top geographies"], "geographies"),
                (["Discourse activity"], "discourse"),
                (["Echo chamber risk"], "echo_risk"),
                (["Articles this cycle"], "articles_count"),
                (["Data sources"], "data_sources"),
            ]:
                for field in fields:
                    val = _extract_li_field(block_html, field)
                    if val:
                        ctx[key] = val
                        break

            # Extract the summary sentence (paragraph after the list)
            # Use .*? instead of [^<]+ so we capture paragraphs containing
            # inline tags like <strong>Moderate</strong>
            summary_match = re.search(
                r"</ul>\s*<p>(.*?)</p>",
                block_html,
                re.DOTALL
            )
            if summary_match:
                ctx["summary"] = _strip_tags(summary_match.group(1)).strip()

            # Extract posture from summary — multiple patterns used by reports:
            #  "X is Strong and is building"
            #  "X standing is strong and is steady"
            #  "X has Insufficient data this cycle"
            #  "X reflects a Strong structural position"
            summary_text = ctx.get("summary", "")
            posture_m = re.search(
                r"(?:is|reflects?\s+(?:a|an)\s+)\s*(Strong|Weak|Mixed|Moderate)(?:\s|,|\.|\band)",
                summary_text, re.IGNORECASE
            )
            if not posture_m:
                posture_m = re.search(
                    r"(?:standing\s+is)\s+(strong|weak|mixed|moderate)",
                    summary_text, re.IGNORECASE
                )
            if not posture_m:
                posture_m = re.search(
                    r"(?:has|is|as)\s+(Insufficient data)",
                    summary_text, re.IGNORECASE
                )
            if posture_m:
                ctx["posture"] = posture_m.group(1).capitalize()

            data["arena_context"][arena_name] = ctx

    # ─── Vulnerability Signals (full details) ───
    vuln_section = re.search(
        r"(?:Sovereign )?Vulnerability Signals.*?</h2>(.*?)(?=<h2|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if vuln_section:
        vuln_html = vuln_section.group(1)
        # Split by h3 tags for each signal
        signal_blocks = re.split(r"<h3>([^<]+)</h3>", vuln_html)
        for i in range(1, len(signal_blocks), 2):
            header = signal_blocks[i].strip()
            block_html = signal_blocks[i + 1] if i + 1 < len(signal_blocks) else ""

            # Parse header: "VS-001 , monarchy_reputation_crisis_signal"
            header_parts = [p.strip() for p in header.split(",")]
            signal_id = header_parts[0] if header_parts else ""
            signal_slug = header_parts[1] if len(header_parts) > 1 else ""
            # Convert slug to title
            signal_title = signal_slug.replace("_", " ").title() if signal_slug else ""

            detail = {
                "id": signal_id,
                "title": signal_title,
                "arena": _extract_li_field(block_html, "Arena"),
                "severity": _extract_li_field(block_html, "Severity"),
                "horizon": _extract_li_field(block_html, "Time horizon"),
                "description": _extract_li_field(block_html, "Why it matters for standing"),
                "structural_position": _extract_li_field(block_html, "Structural position"),
                "mechanism": _extract_li_field(block_html, "Mechanism status"),
                "trend_ref": _extract_li_field(block_html, "Trend reference"),
                "evidence": _extract_li_field(block_html, "Evidence"),
            }
            data["vuln_signal_details"].append(detail)

        data["vulnerability_signals"] = [d["id"] for d in data["vuln_signal_details"]]
        data["vuln_count"] = len(data["vuln_signal_details"])

    # ─── Strength Signals (full details) ───
    strength_section = re.search(
        r"(?:Sovereign )?Strength Signals.*?</h2>(.*?)(?=<h2|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if strength_section:
        str_html = strength_section.group(1)
        signal_blocks = re.split(r"<h3>([^<]+)</h3>", str_html)
        for i in range(1, len(signal_blocks), 2):
            header = signal_blocks[i].strip()
            block_html = signal_blocks[i + 1] if i + 1 < len(signal_blocks) else ""

            # Parse header: "SS-001 , Culture And Media Exports , reputational"
            header_parts = [p.strip() for p in header.split(",")]
            signal_id = header_parts[0] if header_parts else ""
            arena_from_header = header_parts[1] if len(header_parts) > 1 else ""
            character = header_parts[2].title() if len(header_parts) > 2 else ""

            detail = {
                "id": signal_id,
                "arena": _extract_li_field(block_html, "Arena") or arena_from_header,
                "character": _extract_li_field(block_html, "Strength character") or character,
                "horizon": _extract_li_field(block_html, "Time horizon"),
                "description": _extract_li_field(block_html, "Why it reinforces standing"),
                "mechanism": _extract_li_field(block_html, "Mechanism status"),
                "trend_ref": _extract_li_field(block_html, "Trend reference"),
                "evidence": _extract_li_field(block_html, "Evidence"),
            }
            data["strength_signal_details"].append(detail)

        data["strength_signals"] = [d["id"] for d in data["strength_signal_details"]]
        data["strength_count"] = len(data["strength_signal_details"])

    # ─── Strategic Attention Priorities ───
    priorities_section = re.search(
        r"Strategic Attention Priorities.*?</h2>(.*?)(?=<h2|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if priorities_section:
        pri_html = priorities_section.group(1)
        # Split by h3 for time horizons
        horizon_blocks = re.split(r"<h3>(.*?)</h3>", pri_html)
        for i in range(1, len(horizon_blocks), 2):
            horizon = _strip_tags(horizon_blocks[i]).strip()
            block_html = horizon_blocks[i + 1] if i + 1 < len(horizon_blocks) else ""
            # Each priority is a <li>
            for li_match in re.finditer(r"<li>(.*?)</li>", block_html, re.DOTALL):
                li_html = li_match.group(1)
                li_text = _strip_tags(li_html).strip()

                # v2.2 format: "Risk: description... Recommended response: ... Arena: X | Trend: Y"
                risk_match = re.match(
                    r"(?:- )?(Risk|Opportunity|Watch)[:\s]+(.*?)(?:\s*Recommended response:\s*(.*?))?(?:\s*Arena:\s*([\w\s&]+?))?(?:\s*\|\s*Trend:\s*(\S+))?\s*$",
                    li_text, re.DOTALL | re.IGNORECASE
                )
                if risk_match:
                    action = risk_match.group(1).strip()
                    desc = risk_match.group(2).strip().rstrip(",. ")
                    # recommended = risk_match.group(3).strip() if risk_match.group(3) else ""
                    arena = risk_match.group(4).strip() if risk_match.group(4) else ""
                    trend = risk_match.group(5).strip() if risk_match.group(5) else ""
                    data["priorities"].append({
                        "horizon": horizon,
                        "action": action,
                        "arena": arena,
                        "trend": trend,
                        "description": desc,
                    })
                else:
                    # Legacy format: "Action , Arena: X , Trend: Y , Description"
                    parts = [p.strip() for p in li_text.split(",", 3)]
                    action = parts[0].replace("- ", "").strip() if parts else ""
                    arena = ""
                    trend = ""
                    desc = ""
                    for p in parts[1:]:
                        p = p.strip()
                        if p.startswith("Arena:"):
                            arena = p.replace("Arena:", "").strip()
                        elif p.startswith("Trend:"):
                            trend = p.replace("Trend:", "").strip()
                        else:
                            desc = p
                    data["priorities"].append({
                        "horizon": horizon,
                        "action": action,
                        "arena": arena,
                        "trend": trend,
                        "description": desc,
                    })

    # ─── Standing Assessment Overview / Position Summary ───
    overview_section = re.search(
        r"(?:Standing Assessment Overview|Position Summary).*?</h2>(.*?)(?=<h2|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if overview_section:
        section_text = _strip_tags(overview_section.group(1))
        for row in section_text.split("\n"):
            row = row.strip()
            if not row.startswith("|") or row.startswith("|---") or "Dimension" in row:
                continue
            cols = [c.strip() for c in row.split("|")]
            cols = [c for c in cols if c]
            if len(cols) >= 3:
                data["standing_overview"].append({
                    "dimension": cols[0],
                    "assessment": cols[1],
                    "driver": cols[2] if len(cols) > 2 else "",
                })

    # ─── Forward Outlook / Predictions ───
    # Parse predictions_panel or forward_outlook sections if present in RSS
    outlook_section = re.search(
        r"(?:Forward Outlook|Predictions Panel|Prediction Outlook).*?</h[23]>(.*?)(?=<h2|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if outlook_section:
        outlook_raw = outlook_section.group(1)
        section_text = _strip_tags(outlook_raw)

        # Try pipe-delimited table format first (old format)
        table_rows = [r for r in section_text.split("\n") if r.strip().startswith("|") and not r.strip().startswith("|---") and "Title" not in r and "Probability" not in r]
        if table_rows:
            for row in table_rows:
                cols = [c.strip() for c in row.split("|")]
                cols = [c for c in cols if c]
                if len(cols) >= 4:
                    prob_str = cols[1].replace("%", "").strip()
                    try:
                        prob = int(prob_str)
                    except ValueError:
                        prob = None
                    data["predictions"].append({
                        "title": cols[0],
                        "probability": prob,
                        "horizon": cols[2] if len(cols) > 2 else "",
                        "direction": cols[3] if len(cols) > 3 else "",
                        "signal_strength": cols[4] if len(cols) > 4 else "",
                        "trigger": cols[5] if len(cols) > 5 else "",
                    })
        else:
            # v2.2 prose-based format: <h3>Arena</h3><p>...XX% probability...Intensifying...30 days...</p>
            outlook_blocks = re.split(r"<h3>(.*?)</h3>", outlook_raw)
            for i in range(1, len(outlook_blocks), 2):
                arena_name = _strip_tags(outlook_blocks[i]).strip()
                block_html = outlook_blocks[i + 1] if i + 1 < len(outlook_blocks) else ""
                block_text = _strip_tags(block_html).strip()

                # Extract ALL probability mentions from the prose (not just the first)
                # Match both "XX% probability of Intensifying" and "XX% intensification probability"
                prob_matches = re.findall(
                    r"(\d+)%\s*(?:probability\s+of\s+)?(Intensifying|Stable|Fading|Reversing|intensification)",
                    block_text, re.IGNORECASE
                )
                # Extract signal strength
                signal_m = re.search(r"\((Strong|Moderate|Thin)\s+signal\)", block_text, re.IGNORECASE)
                signal = signal_m.group(1) if signal_m else ""
                # Extract trigger / what would change it — broader patterns
                trigger_m = re.search(
                    r"(?:arrested if|unless|change.?(?:if|when)|would change it[:\s]*|What would change it[:\s]*)\s*(.*?)(?:\.|$)",
                    block_text, re.IGNORECASE
                )
                trigger = trigger_m.group(1).strip() if trigger_m else ""
                # If trigger still empty, look for "momentum returns" style phrasing
                if not trigger:
                    trigger_m2 = re.search(r"(?:momentum\s+returns|visibility\s+expands|attention\s+shifts|public commentary)\s*[^.]*", block_text, re.IGNORECASE)
                    if trigger_m2:
                        trigger = trigger_m2.group(0).strip()

                # Extract ALL horizons from the prose
                horizon_matches = re.findall(r"(?:next|over the next|within)\s+(\d+\s*(?:days?|months?|years?))", block_text, re.IGNORECASE)

                if prob_matches:
                    # Store EACH probability as a separate prediction
                    for idx, (prob_str, direction_raw) in enumerate(prob_matches):
                        prob = int(prob_str)
                        direction = "Intensifying" if "intensif" in direction_raw.lower() else direction_raw.capitalize()
                        # Match horizon to this prediction (by index or nearest)
                        horizon = horizon_matches[idx] if idx < len(horizon_matches) else (horizon_matches[-1] if horizon_matches else "")
                        title = f"{arena_name} outlook"
                        data["predictions"].append({
                            "title": title,
                            "probability": prob,
                            "horizon": horizon,
                            "direction": direction,
                            "signal_strength": signal,
                            "trigger": trigger if idx == 0 else "",
                            "type": "",
                        })
                    # Store the LEAD (highest) probability as the arena prediction
                    lead_prob = max(int(p[0]) for p in prob_matches)
                    data["arena_predictions"][arena_name] = {
                        "has_outlook": True,
                        "outlook_sentence": block_text[:300],
                        "probability": lead_prob,
                    }

    # Parse per-arena prediction outlook sentences
    arena_outlook_matches = re.finditer(
        r"(?:Arena Prediction Outlook|Arena Outlook)[^:]*?:\s*([^\n<]+)",
        desc_html, re.IGNORECASE
    )
    for m in arena_outlook_matches:
        text = _strip_tags(m.group(1)).strip()
        # Try to extract arena name and outlook sentence
        arena_match = re.match(r"(\w[\w\s&]+?)\s*[-:]\s*(.+)", text)
        if arena_match:
            arena_name = arena_match.group(1).strip()
            outlook_sentence = arena_match.group(2).strip()
            data["arena_predictions"][arena_name] = {
                "has_outlook": True,
                "outlook_sentence": outlook_sentence,
            }

    # ─── Section 5: Sovereign Profile Snapshot ───
    profile_section = re.search(
        r"(?:Sovereign )?Profile Snapshot.*?</h[23]>(.*?)(?=<h2|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if profile_section:
        profile_html = profile_section.group(1)
        profile_data = {}
        # Parse sub-sections (h3 blocks with pipe-delimited tables)
        sub_sections = re.split(r"<h3[^>]*>(.*?)</h3>", profile_html)
        for i in range(1, len(sub_sections), 2):
            sub_title = _strip_tags(sub_sections[i]).strip()
            sub_content = sub_sections[i + 1] if i + 1 < len(sub_sections) else ""
            # Parse pipe-delimited table rows
            rows = []
            for line in sub_content.split("\n"):
                line = _strip_tags(line).strip()
                if "|" in line and not line.startswith("|--") and not line.startswith("| Field"):
                    cols = [c.strip() for c in line.split("|") if c.strip()]
                    if len(cols) >= 2:
                        rows.append({"field": cols[0], "detail": cols[1]})
                    elif len(cols) == 3:
                        rows.append({"field": cols[0], "detail": cols[1], "note": cols[2]})
            if rows:
                profile_data[sub_title] = rows
        data["profile_snapshot"] = profile_data

    # ─── Section 9: Structural Contradictions ───
    contradictions_section = re.search(
        r"Structural Contradictions.*?</h2>(.*?)(?=<h2|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if contradictions_section:
        data["structural_contradictions"] = _strip_tags(contradictions_section.group(1)).strip()

    # ─── Section 10: Standing Diagnostic Coverage ───
    diagnostic_section = re.search(
        r"(?:Standing )?Diagnostic Coverage.*?</h2>(.*?)(?=<h2|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if diagnostic_section:
        diag_html = diagnostic_section.group(1)
        diag_rows = []
        for line in diag_html.split("\n"):
            line_text = _strip_tags(line).strip()
            if "|" in line_text and not line_text.startswith("|--") and "---" not in line_text:
                cols = [c.strip() for c in line_text.split("|") if c.strip()]
                # Skip header row (first col is exactly "Diagnostic prompt" without colon)
                if cols and cols[0] == "Diagnostic prompt":
                    continue
                if len(cols) >= 3 and cols[0].startswith("Diagnostic prompt"):
                    prompt_name = cols[0].replace("Diagnostic prompt:", "").replace("Diagnostic prompt", "").strip()
                    diag_rows.append({
                        "prompt": prompt_name,
                        "coverage": cols[1] if len(cols) > 1 else "",
                        "clear": cols[2] if len(cols) > 2 else "",
                        "bounded": cols[3] if len(cols) > 3 else "",
                    })
        # Also capture any trailing text (uncovered diagnostic narrative)
        trailing = re.findall(r"</p>\s*<p>([^<|]+(?:Not covered|not confirmed)[^<]*)</p>", diag_html, re.DOTALL)
        if trailing:
            for t in trailing:
                text = _strip_tags(t).strip()
                if text:
                    diag_rows.append({"prompt": text[:80], "coverage": "Not covered", "clear": "", "bounded": text})
        data["diagnostic_coverage"] = diag_rows

    # ─── Conclusion ───
    conclusion_match = re.search(
        r"<h2[^>]*>[^<]*Conclusion[^<]*</h2>(.*?)(?=<h2|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if conclusion_match:
        data["conclusion"] = _strip_tags(conclusion_match.group(1))

    # ─── Score & Posture Extraction ───
    # Primary: perception dashboard average (sovereign_view if available, else global_view)
    if data["perception_dashboard"]:
        # Check if we have arena-grouped data — if so, use arena summary rows only
        has_arena_groups = any(p.get("is_arena_summary") for p in data["perception_dashboard"])
        if has_arena_groups:
            # Use arena summary rows for score (avoids double-counting propositions)
            arena_scores = [p["global_view"] for p in data["perception_dashboard"]
                           if p.get("is_arena_summary") and p.get("global_view") is not None]
            if arena_scores:
                data["score"] = round(sum(arena_scores) / len(arena_scores))
        else:
            sv_scores = [p["sovereign_view"] for p in data["perception_dashboard"] if p.get("sovereign_view") is not None]
            if sv_scores:
                data["score"] = round(sum(sv_scores) / len(sv_scores))
            else:
                # v2.2 reports have only global_view (External Perception)
                gv_scores = [p["global_view"] for p in data["perception_dashboard"] if p.get("global_view") is not None]
                if gv_scores:
                    data["score"] = round(sum(gv_scores) / len(gv_scores))

    # Fallback 1: "score: 74/100" format from exec summary
    if data["score"] is None:
        score_match = re.search(r"(?:score|standing)[:\s]*(\d{1,3})\s*/\s*100", desc_html, re.IGNORECASE)
        if score_match:
            data["score"] = int(score_match.group(1))

    # Fallback 2: "overall score: 74" or "overall score of 70" (without /100)
    if data["score"] is None:
        score_match2 = re.search(r"overall\s+score[:\s]+(?:of\s+)?(\d{1,3})", desc_html, re.IGNORECASE)
        if score_match2:
            val = int(score_match2.group(1))
            if 0 <= val <= 100:
                data["score"] = val

    # Posture extraction: prioritize the authoritative "Standing posture this cycle:" from conclusion
    # This is the 7A decision — takes precedence over general "perceived as" matches
    conclusion_posture = re.search(
        r"Standing posture this cycle[:\s]*</strong>\s*(Strong|Mixed|Moderate|Weak|Declining|Under pressure|Stable|Under Pressure)",
        desc_html, re.IGNORECASE
    )
    if not conclusion_posture:
        conclusion_posture = re.search(
            r"Standing posture this cycle[:\s]*(Strong|Mixed|Moderate|Weak|Declining|Under pressure|Stable)",
            _strip_tags(data.get("conclusion", "")), re.IGNORECASE
        )
    if conclusion_posture:
        data["posture"] = conclusion_posture.group(1).strip().capitalize()
        # Normalize "Under pressure" to title case
        if data["posture"].lower() == "under pressure":
            data["posture"] = "Under pressure"
    else:
        # Fallback: general regex on full HTML
        posture_match = re.search(
            r"(?:perceived as|posture[:\s]*|standing[:\s]*)\s*(strong|mixed|moderate|weak|declining|under pressure|stable)",
            desc_html, re.IGNORECASE
        )
        if posture_match:
            data["posture"] = posture_match.group(1).capitalize()

    # Fallback from trend count if we didn't parse individual trends
    if data["trend_count"] == 0:
        # Count unique TRU-* IDs (more accurate than T\d+ which double-counts)
        tru_ids = set(re.findall(r"TRU-\w+", desc_html))
        if tru_ids:
            data["trend_count"] = len(tru_ids)
        else:
            # Older format: count unique T-id patterns
            trend_matches = set(re.findall(r"TRU-T\d+|T\d+(?=\s*\|)", desc_html))
            data["trend_count"] = len(trend_matches)

    # Fallback signal counts from ID matching if detailed parsing missed them
    if data["strength_count"] == 0:
        ss_section = re.search(r"(?:Sovereign )?Strength Signals(.*?)(?=<h2|$)", desc_html, re.DOTALL | re.IGNORECASE)
        if ss_section:
            ss_ids = re.findall(r"SS-\d+", ss_section.group(1))
            data["strength_count"] = len(set(ss_ids))
            if not data["strength_signals"]:
                data["strength_signals"] = list(dict.fromkeys(ss_ids))

    if data["vuln_count"] == 0:
        vs_section = re.search(r"(?:Sovereign )?Vulnerability Signals(.*?)(?=<h2|Structural|$)", desc_html, re.DOTALL | re.IGNORECASE)
        if vs_section:
            vs_ids = re.findall(r"VS-\d+", vs_section.group(1))
            data["vuln_count"] = len(set(vs_ids))
            if not data["vulnerability_signals"]:
                data["vulnerability_signals"] = list(dict.fromkeys(vs_ids))

    # v2.2: Extract strength/vulnerability counts AND details from Standing Context
    # when inline within arena blocks (Reinforcing/Pressure sub-sections)
    ctx_section = re.search(
        r"(?:Sovereign )?Standing Context.*?</h2>(.*?)(?=<h2|$)",
        desc_html, re.DOTALL | re.IGNORECASE
    )
    if ctx_section:
        ctx_html = ctx_section.group(1)
        # Split by arena headers (h4 tags) to attribute signals to arenas
        arena_blocks = re.split(r"<h4[^>]*>(.*?)</h4>", ctx_html)
        current_arena = ""
        inline_ss_total = 0
        inline_vs_total = 0
        for i in range(1, len(arena_blocks), 2):
            current_arena = _strip_tags(arena_blocks[i]).strip()
            block = arena_blocks[i + 1] if i + 1 < len(arena_blocks) else ""

            # Extract "Pressure on this standing" signals
            pressure_match = re.findall(
                r"Pressure on this standing.*?(?=Reinforcing|<h4|<h3|$)",
                block, re.DOTALL | re.IGNORECASE
            )
            for pb in pressure_match:
                # Parse each bullet: "* <strong>SEVERITY , HORIZON:</strong> DESCRIPTION"
                bullets = re.findall(
                    r"(?:<li>|^\*)\s*(?:<strong>)?\s*(\w+)\s+severity\s*(?:,|—|\u2014)\s*(\w+)[:\s]*(?:</strong>)?\s*(.*?)(?=<li>|^\*|\Z)",
                    pb, re.DOTALL | re.MULTILINE | re.IGNORECASE
                )
                for sev, horizon, desc_raw in bullets:
                    desc_clean = _strip_tags(desc_raw).strip().rstrip(")")
                    # Truncate at evidence references
                    evd_pos = desc_clean.find("(EVD-")
                    if evd_pos > 0:
                        desc_clean = desc_clean[:evd_pos].strip()
                    data["vuln_signal_details"].append({
                        "severity": sev.capitalize(),
                        "horizon": horizon.capitalize(),
                        "description": desc_clean,
                        "arena": current_arena,
                    })
                    inline_vs_total += 1

            # Extract "Reinforcing this standing" signals
            reinforcing_match = re.findall(
                r"Reinforcing this standing.*?(?=Pressure on|<h4|<h3|$)",
                block, re.DOTALL | re.IGNORECASE
            )
            for rb in reinforcing_match:
                bullets = re.findall(
                    r"(?:<li>|^\*)\s*(?:<strong>)?\s*(\w+)\s+(?:character|strength)\s*(?:,|—|\u2014)\s*(\w+)[:\s]*(?:</strong>)?\s*(.*?)(?=<li>|^\*|\Z)",
                    rb, re.DOTALL | re.MULTILINE | re.IGNORECASE
                )
                for char, horizon, desc_raw in bullets:
                    desc_clean = _strip_tags(desc_raw).strip().rstrip(")")
                    evd_pos = desc_clean.find("(EVD-")
                    if evd_pos > 0:
                        desc_clean = desc_clean[:evd_pos].strip()
                    data["strength_signal_details"].append({
                        "character": char.capitalize(),
                        "horizon": horizon.capitalize(),
                        "description": desc_clean,
                        "arena": current_arena,
                    })
                    inline_ss_total += 1

        # Update counts if not already set from standalone sections
        if data["strength_count"] == 0 and inline_ss_total > 0:
            data["strength_count"] = inline_ss_total
        if data["vuln_count"] == 0 and inline_vs_total > 0:
            data["vuln_count"] = inline_vs_total

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
        data["score"] = 50
        if data["posture"] is None:
            data["posture"] = "Mixed"

    return data


def fetch_predictions_from_rendered(guid):
    """
    Fetch the rendered report page at makes.news/view/{guid} and
    scrape prediction tiles from the Forward Outlook section.
    Returns (predictions_list, arena_predictions_dict).
    """
    if not guid:
        return [], {}

    url = "https://sovereignsignal.makes.news/view/" + guid
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SovereignSignal/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw_html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"      Warning: Could not fetch rendered report ({e})")
        return [], {}

    # Strip HTML tags for text-based parsing
    text = re.sub(r"<[^>]+>", "\n", raw_html)
    text = re.sub(r"\n+", "\n", text)

    # ─── Parse prediction tiles ───
    # Tile layout from rendered reports:
    #   XX% probability
    #   Title text
    #   Direction (Intensifying|Stable|Fading|Reversing)
    #   [optional: Strength|Vulnerability type]
    #   Signal strength (Strong|Thin|Medium)
    #   [optional whitespace]
    #   Horizon (90 days, 12 months, etc.)
    #   What would change it: trigger text
    predictions = []
    blocks = re.findall(
        r"(\d+)%\s*probability\s*\n\s*"
        r"([^\n]+)\s*\n\s*"
        r"(Intensifying|Stable|Fading|Reversing)\s*\n\s*"
        r"(?:(Strength|Vulnerability)\s*\n\s*)?"
        r"(Strong|Thin|Medium)\s*\n\s*"
        r"(\d+\s*(?:days?|months?))\s*\n\s*"
        r"(?:What would change it:\s*)?([^\n]+)",
        text, re.IGNORECASE,
    )
    for b in blocks:
        predictions.append({
            "title": b[1].strip(),
            "probability": int(b[0]),
            "type": (b[3] or "").strip(),
            "direction": b[2].strip(),
            "signal_strength": b[4].strip(),
            "horizon": b[5].strip(),
            "trigger": b[6].strip(),
        })

    # ─── Parse per-arena outlook sentences ───
    arena_preds = {}
    arena_matches = re.findall(
        r"(?:We assess|Current framing)[^.]*?(\d+)%\s*probability[^.]*?"
        r"(?:that\s+)?([A-Z][a-zA-Z\s&]+?)(?:\s+narratives?\s+|\s+posture\s+)"
        r"([^.]+)",
        text,
    )
    for prob_str, arena_name, rest in arena_matches:
        arena_preds[arena_name.strip()] = {
            "has_outlook": True,
            "outlook_sentence": "{}% probability that {} narratives {}".format(
                prob_str, arena_name.strip(), rest.strip()
            ),
            "probability": int(prob_str),
        }

    # ─── Parse perception dashboard from rendered page ───
    # The rendered page often has the full table with Sovereign View,
    # which may be absent or different in the RSS description.
    # v2.2 format: arena-grouped with 4 fields per row (Proposition, Sovereign View, Signal, Emerging)
    # Old format: 5-6 fields per row (Proposition, Global View, [Sovereign View], Confidence, Arena, Emerging)
    rendered_perception = []
    pd_section = re.search(
        r"SOVEREIGN PERCEPTION DASHBOARD(.*?)(?:ARENA ANALYSIS|TREND MATRIX|FORWARD OUTLOOK|SOVEREIGN PROFILE|POSITION SUMMARY|COMPASS NOTES|SOVEREIGN STANDING|$)",
        text, re.DOTALL | re.IGNORECASE
    )
    if pd_section:
        pd_text = pd_section.group(1)
        pd_lines = [l.strip() for l in pd_text.split("\n") if l.strip()]
        # Detect format from header fields — only match exact header lines, not prose
        has_sv = any(l == "Sovereign View" or l == "Sovereign View %" for l in pd_lines[:10])
        has_gv = any(l in ("Global View", "Global View %", "External Perception", "External Perception %") for l in pd_lines[:10])
        has_arena_col = any(l == "Arena" for l in pd_lines[:10])
        # v2.2 arena-grouped: headers are Proposition, Sovereign View, Signal Strength, Emerging (4 fields, no Arena col)
        is_v22_grouped = has_sv and not has_arena_col and not has_gv
        # Find header row index — match exact "Proposition" header, not prose containing the word
        header_idx = None
        for i, l in enumerate(pd_lines):
            if l == "Proposition" or (l == "Arena" and i < 10):
                header_idx = i
                break
        if header_idx is not None:
            if is_v22_grouped:
                # v2.2 arena-grouped: 4 header fields, then 4 fields per row
                # Headers: Proposition | Sovereign View | Signal Strength | Emerging
                # Data: arena name or └ proposition | XX% | Strong/Thin/Medium | — or ✓
                data_start = header_idx + 4
                data_lines = pd_lines[data_start:]
                row_data = []
                current_arena = ""
                for l in data_lines:
                    row_data.append(l)
                    if len(row_data) == 4:
                        prop_name = row_data[0]
                        sv_str = row_data[1].replace("%", "").strip()
                        signal = row_data[2]
                        emerging = row_data[3]
                        try:
                            sv = int(sv_str)
                        except ValueError:
                            sv = None
                        # Detect arena summary vs proposition
                        is_arena = not prop_name.startswith("\u2514") and not prop_name.startswith("&lfloor;")
                        clean_name = prop_name.replace("\u2514", "").replace("&lfloor;", "").replace("&amp;", "&").strip()
                        if is_arena:
                            current_arena = clean_name
                        if sv is not None:
                            rendered_perception.append({
                                "proposition": clean_name,
                                "global_view": sv,  # Use SV as the primary score
                                "sovereign_view": sv,
                                "signal_strength": signal,
                                "arena": current_arena if not is_arena else clean_name,
                                "emerging": emerging.strip(", "),
                                "is_arena_summary": is_arena,
                            })
                        row_data = []
                    # Stop if we hit a section break
                    elif len(row_data) == 1 and (
                        row_data[0].startswith("External Perception") or
                        row_data[0].startswith("Compass Notes") or
                        row_data[0].startswith("Propositions are grouped")
                    ):
                        row_data = []
                        break
            else:
                # Old format: 5-6 fields per row
                data_start = header_idx + (6 if has_sv else 5)
                fields_per_row = 6 if has_sv else 5
                data_lines = pd_lines[data_start:]
                row_data = []
                for l in data_lines:
                    row_data.append(l)
                    if len(row_data) == fields_per_row:
                        prop = row_data[0]
                        gv_str = row_data[1].replace("%", "").strip()
                        if has_sv:
                            sv_str = row_data[2].replace("%", "").strip()
                            conf = row_data[3]
                            arena = row_data[4]
                            emerging = row_data[5] if len(row_data) > 5 else ""
                        else:
                            sv_str = ""
                            conf = row_data[2]
                            arena = row_data[3]
                            emerging = row_data[4] if len(row_data) > 4 else ""
                        try:
                            gv = int(gv_str)
                        except ValueError:
                            gv = None
                        try:
                            sv = int(sv_str)
                        except ValueError:
                            sv = None
                        # Only include rows where at least one score parsed
                        if gv is not None or sv is not None:
                            rendered_perception.append({
                                "proposition": prop,
                                "global_view": gv,
                                "sovereign_view": sv,
                                "signal_strength": conf,
                                "arena": arena,
                                "emerging": emerging.strip(", "),
                            })
                        row_data = []
                    # Stop if we hit a non-data line
                    elif len(row_data) == 1 and row_data[0].startswith("External Perception"):
                        row_data = []

    return predictions, arena_preds, rendered_perception


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

    # "assessed as Strong in X and Y" or "Strong in both X and Y"
    for m in re.finditer(
        r'Strong\s+in\s+(?:both\s+)?([A-Z][A-Za-z,\s&]+?)(?:\s*(?:,\s*(?:with|while|but)|\.|;))',
        combined
    ):
        for arena in _split_arena_list(m.group(1)):
            if arena not in seen:
                seen.add(arena)
                findings.append({"arena": arena, "posture": "Strong", "detail": ""})

    # "strength-weighted standing in X and Y"
    for m in re.finditer(
        r'strength-weighted\s+(?:standing|picture)\s+in\s+([A-Z][A-Za-z,\s&]+?)(?:\s*(?:,\s*(?:with|while|but)|\.|;))',
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

    # Generate OG sharing image
    _generate_og_image(display_date, composite, composite_posture, pillar_data)


def _generate_og_image(display_date, composite, composite_posture, pillar_data):
    """Generate og-image.html with live scores, then capture as og-card.png via headless Chrome."""
    import shutil

    og_html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: 1200px; height: 630px; overflow: hidden; background: #1a1e27; }}
.card {{ width: 1200px; height: 630px; background: #1a1e27; position: relative; overflow: hidden; display: flex; flex-direction: column; align-items: center; justify-content: center; }}
.flag {{ position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: url('og-flag.png') center center / cover no-repeat; opacity: 0.4; filter: saturate(0.5) contrast(1.1); }}
.overlay {{ position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(26,30,39,0.55); }}
.brand {{ position: relative; z-index: 2; text-align: center; margin-top: -30px; }}
.title {{ font-family: 'Montserrat', sans-serif; font-size: 130px; font-weight: 700; color: #FFFFFF; letter-spacing: 0.30em; text-transform: uppercase; }}
.subtitle {{ font-family: 'Lora', Georgia, serif; font-size: 48px; font-weight: 400; font-style: italic; color: rgba(255,255,255,0.7); letter-spacing: 0.12em; margin-top: 16px; }}
</style>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@700;800&family=Lora:ital,wght@0,400;1,400&display=swap" rel="stylesheet">
</head>
<body>
<div class="card">
  <div class="flag"></div>
  <div class="overlay"></div>
  <div class="brand">
    <div class="title">DIPTEL</div>
    <div class="subtitle">Sovereign Signal</div>
  </div>
</div>
</body></html>"""

    og_html_path = SCRIPT_DIR / "og-image.html"
    with open(og_html_path, "w") as f:
        f.write(og_html)

    # Try to capture PNG via headless Chrome
    chrome_path = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome_path:
        # macOS Chrome path
        mac_chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(mac_chrome):
            chrome_path = mac_chrome

    if chrome_path:
        og_png_path = SCRIPT_DIR / "og-card.png"
        try:
            import subprocess
            result = subprocess.run([
                chrome_path,
                "--headless=new",
                "--disable-gpu",
                f"--screenshot={og_png_path}",
                "--window-size=1200,630",
                "--hide-scrollbars",
                "--virtual-time-budget=5000",
                f"file://{og_html_path}",
            ], capture_output=True, text=True, timeout=30)
            if og_png_path.exists() and og_png_path.stat().st_size > 10000:
                print(f"  OG sharing image written: og-card.png ({og_png_path.stat().st_size // 1024}KB)")
            else:
                print(f"  Warning: OG image may not have rendered correctly")
        except Exception as e:
            print(f"  Warning: Could not generate OG PNG: {e}")
    else:
        print(f"  OG HTML template written (no Chrome found for PNG capture)")


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
    if p in ("weak", "declining", "under pressure"):
        return "weak"
    if p in ("stable",):
        return "stable"
    return "mixed"


def _score_color(score):
    """Return CSS color variable for a score: red if <50, green if >=50."""
    if score is None:
        return "var(--text-muted)"
    return "var(--green)" if score >= 50 else "var(--red)"


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

    # Composite score number — stock-style: green if up, red if down
    # On first cycle (no delta), derive colour from score vs 50 midpoint
    if composite_delta is not None and composite_delta > 0:
        composite_num_color = "var(--green)"
    elif composite_delta is not None and composite_delta < 0:
        composite_num_color = "var(--red)"
    else:
        # First cycle — use score vs midpoint so it never looks blank
        composite_num_color = "var(--green)" if (composite or 0) >= 50 else "var(--red)"

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

        # Previous score display
        prev_score = prev_pillar_scores.get(key)
        if prev_score is not None and delta is not None:
            prev_color = "var(--green)" if delta >= 0 else "var(--red)"
            prev_html = f'<div class="pillar-score-prev" style="color:{prev_color}">{prev_score}</div>'
        else:
            prev_html = '<div class="pillar-score-prev">&mdash;</div>'

        # Stock-style colouring: green if up, red if down
        # On first cycle (no delta), derive colour from score vs 50 midpoint
        if delta is not None and delta > 0:
            score_color = "var(--green)"
        elif delta is not None and delta < 0:
            score_color = "var(--red)"
        else:
            score_color = "var(--green)" if (score or 0) >= 50 else "var(--red)"
        report_href = f"uk-{key}-{target_date}.html"
        # Directional triangle for score
        if delta is not None and delta > 0:
            score_arrow = f' <span style="font-size:0.5em;vertical-align:middle">&#9650;</span>'
        elif delta is not None and delta < 0:
            score_arrow = f' <span style="font-size:0.5em;vertical-align:middle">&#9660;</span>'
        else:
            score_arrow = ""
        pillar_score_cells += f'''
      <a class="pillar-score-cell{" " + cell_cls if cell_cls else ""}" data-pillar="{key}" href="{report_href}">
        <div class="pillar-score-name">{pillar["name"]}</div>
        <div class="pillar-score-num" style="color:{score_color}">{score_display}{score_arrow}</div>
        {prev_html}
        <div class="pillar-score-posture">{post}</div>
      </a>'''

    # Build briefing cards — one horizontal card per pillar with all findings
    # Sort worst-first (lowest score first) for editorial emphasis
    briefing_cards_html = ""
    total_strengths = 0
    total_vulns = 0
    sorted_pillar_keys = sorted(
        PILLARS.keys(),
        key=lambda k: pillar_data.get(k, {}).get("score") or 999
    )
    for key in sorted_pillar_keys:
        pillar = PILLARS[key]
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

        # Merge with arena_context for momentum data
        arena_ctx = pdata.get("arena_context", {})

        # Re-derive posture from summaries if missing (handles saved JSON without posture)
        for arena_name, ctx in arena_ctx.items():
            if "posture" not in ctx and "summary" in ctx:
                summary_text = ctx["summary"]
                pm = re.search(r"(?:is|reflects?\s+(?:a|an)\s+)\s*(Strong|Weak|Mixed|Moderate)(?:\s|,|\.|\band)", summary_text, re.IGNORECASE)
                if not pm:
                    pm = re.search(r"(?:standing\s+is)\s+(strong|weak|mixed|moderate)", summary_text, re.IGNORECASE)
                if not pm:
                    pm = re.search(r"(?:has|is|as)\s+(Insufficient data)", summary_text, re.IGNORECASE)
                if pm:
                    ctx["posture"] = pm.group(1).capitalize()

        # Override findings posture with arena_context posture (more reliable than regex extraction)
        for f in findings:
            ctx = arena_ctx.get(f["arena"], {})
            if ctx.get("posture"):
                f["posture"] = ctx["posture"].capitalize()

        # Supplement findings with any arena_context entries the regex missed
        if arena_ctx:
            found_names = {f["arena"] for f in findings}
            for arena_name, ctx in arena_ctx.items():
                if arena_name not in found_names:
                    ap = ctx.get("posture", "")
                    if ap.lower() in ("strong",):
                        findings.append({"arena": arena_name, "posture": "Strong", "detail": ""})
                    elif ap.lower() in ("weak",):
                        findings.append({"arena": arena_name, "posture": "Weak", "detail": ""})
                    elif ap.lower() in ("moderate", "mixed"):
                        findings.append({"arena": arena_name, "posture": "Mixed", "detail": ""})
                    elif ap.lower() in ("insufficient data",):
                        findings.append({"arena": arena_name, "posture": "Uncertain", "detail": "Insufficient data"})
                    else:
                        findings.append({"arena": arena_name, "posture": "Uncertain", "detail": ap})

        # Build finding rows — each arena gets its own row in the card
        findings_rows_html = ""
        if findings:
            for f in findings:
                posture = f["posture"]
                if posture.lower() in ("strong",):
                    dot_cls = "finding-dot-strong"
                    badge_cls = "finding-badge-strong"
                    posture = "Strong"
                elif posture.lower() in ("weak",):
                    dot_cls = "finding-dot-weak"
                    badge_cls = "finding-badge-weak"
                    posture = "Weak"
                elif posture.lower() in ("mixed", "moderate"):
                    dot_cls = "finding-dot-mixed"
                    badge_cls = "finding-badge-mixed"
                    posture = "Mixed"
                elif posture.lower() in ("insufficient data",):
                    dot_cls = "finding-dot-uncertain"
                    badge_cls = "finding-badge-uncertain"
                    posture = "Low Data"
                else:
                    dot_cls = "finding-dot-uncertain"
                    badge_cls = "finding-badge-uncertain"

                # Look up momentum from arena_context
                ctx = arena_ctx.get(f["arena"], {})
                momentum = ctx.get("momentum", "")
                mom_html = ""
                if momentum:
                    if momentum.lower() == "rising":
                        mom_html = ' <span class="finding-momentum finding-mom-rising">&#9650;</span>'
                    elif momentum.lower() == "fading":
                        mom_html = ' <span class="finding-momentum finding-mom-fading">&#9660;</span>'
                    else:
                        mom_html = ' <span class="finding-momentum">&#8594;</span>'

                findings_rows_html += f'''
              <div class="finding-row">
                <span class="finding-dot {dot_cls}"></span>
                <span class="finding-arena">{html.escape(f["arena"])}</span>{mom_html}
                <span class="finding-badge {badge_cls}">{posture}</span>
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

        # Key prediction — show the highest-probability prediction for this pillar
        key_pred_html = ""
        pillar_preds = pdata.get("predictions", [])
        if pillar_preds:
            top_pred = max(pillar_preds, key=lambda p: p.get("probability") or 0)
            tp_prob = top_pred.get("probability")
            tp_title = top_pred.get("title", "")
            tp_type = top_pred.get("type", "")
            tp_horizon = top_pred.get("horizon", "")
            tp_type_cls = "key-pred-vuln" if "vuln" in tp_type.lower() else "key-pred-strength"
            key_pred_html = f'''
        <div class="key-pred-row">
          <span class="key-pred-icon">&#9670;</span>
          <span class="key-pred-prob">{tp_prob}%</span>
          <span class="key-pred-text">{html.escape(tp_title)}</span>
          <span class="key-pred-badge {tp_type_cls}">{html.escape(tp_type)}</span>
          <span class="key-pred-horizon">{html.escape(tp_horizon)}</span>
        </div>'''

        # Briefing card score arrow
        bc_delta = deltas.get(key)
        if bc_delta is not None and bc_delta > 0:
            bc_arrow = ' <span style="font-size:0.55em;vertical-align:middle">&#9650;</span>'
            bc_color = "var(--green)"
        elif bc_delta is not None and bc_delta < 0:
            bc_arrow = ' <span style="font-size:0.55em;vertical-align:middle">&#9660;</span>'
            bc_color = "var(--red)"
        else:
            bc_arrow = ""
            bc_color = "var(--green)" if isinstance(score, int) and score >= 50 else "var(--red)" if isinstance(score, int) else "var(--text)"

        briefing_cards_html += f'''
      <a class="briefing-card" data-pillar="{key}" id="tile-{key}" href="{href}">
        <div class="briefing-card-top">
          <div class="briefing-card-left">
            <span class="briefing-card-tag">{pillar["short"]}</span>
            <span class="briefing-card-title">{pillar["name"]}</span>
          </div>
          <div class="briefing-card-stats">
            <div class="briefing-card-score" style="color:{bc_color}">{score_display}{bc_arrow}</div>
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
        </div>{key_pred_html}
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
<title>Sovereign Signal — Sentiment, Trends &amp; Predictions</title>
<meta property="og:title" content="Sovereign Signal — Sentiment, Trends & Predictions">
<meta property="og:description" content="Daily intelligence on the United Kingdom's external positioning — sentiment analysis, trend monitoring, and forward predictions across five strategic pillars.">
<meta property="og:image" content="https://ivanmassow.github.io/client-reports/sovereign-signal/og-card.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:type" content="website">
<meta property="og:url" content="https://ivanmassow.github.io/client-reports/sovereign-signal/">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Sovereign Signal — Sentiment, Trends & Predictions">
<meta name="twitter:description" content="Daily intelligence — sentiment, trends & predictions">
<meta name="twitter:image" content="https://ivanmassow.github.io/client-reports/sovereign-signal/og-card.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Lora:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
{css}
</style>
</head>
<body>

<div class="topbar">
  <div class="topbar-left">
    <a href="index.html" class="topbar-logo" style="text-decoration:none;color:rgba(255,255,255,0.9)">DipTel</a>
    <div class="topbar-divider"></div>
    <a href="index.html" style="text-decoration:none"><span class="topbar-brand">Sovereign Signal</span></a>
    <div class="topbar-divider"></div>
    <nav class="topbar-nav">
      <a href="#" class="active">Dashboard</a>
      <a href="#pillars">Intelligence Briefings</a>
    </nav>
  </div>
  <div class="topbar-right">
    <span class="topbar-date" id="topbar-date">{display_date}</span>
  </div>
</div>

<div class="hero">
  <div class="hero-bg"></div>
  <div class="hero-inner">
    <div class="hero-left">
      <div class="hero-eyebrow">United Kingdom</div>
      <h1 class="hero-title">Sovereign<br>Signal Overview</h1>
      <div class="hero-subtitle">Sentiment, Trends &amp; Predictions</div>
      <p class="hero-desc">Daily intelligence tracking the United Kingdom&rsquo;s external positioning &mdash; sentiment analysis, trend monitoring, and forward predictions across five strategic pillars.</p>
      <div class="hero-date-nav">
        <a class="date-arrow{" disabled" if not prev_date_link else ""}" id="date-prev" title="Previous day">&larr;</a>
        <span class="date-label" id="hero-date">{display_date}</span>
        <a class="date-arrow disabled" id="date-next" title="Next day">&rarr;</a>
      </div>
    </div>
    <div class="score-block">
      <div class="score-block-inner">
        <div class="score-block-label">Composite Sentiment Score</div>
        <div class="score-block-num" id="composite-score" style="color:{composite_num_color}">{composite}{' <span style="font-size:0.45em;vertical-align:middle">&#9650;</span>' if composite_delta and composite_delta > 0 else ' <span style="font-size:0.45em;vertical-align:middle">&#9660;</span>' if composite_delta and composite_delta < 0 else ''}</div>
        <div class="score-block-max">of 100</div>
        <div class="score-block-delta {sb_delta_cls}">{sb_delta_content}</div>
        <div class="score-block-posture posture-{posture_cls}" id="composite-posture">{composite_posture}</div>
      </div>
    </div>
  </div>
</div>

<div class="pillar-scores" id="pillar-scores">{pillar_score_cells}
</div>

<div class="container">
  <div id="pillars">
    <div class="section-head">
      <h2 class="section-title">Daily Intelligence Briefings</h2>
      <span class="section-meta">Cycle: {display_date} &middot; {total_strengths} strengths &middot; {total_vulns} vulnerabilities</span>
    </div>
    <div class="briefing-cards">{briefing_cards_html}
    </div>
  </div>
</div>

<div class="methodology-box">
  <div class="methodology-box-inner">
    <div class="methodology-box-text">Sovereign Signal applies narrative signal processing to over 1.6 million sources daily &mdash; reducing billions of data points into actionable intelligence on sentiment, trends, and predictions.</div>
    <a class="methodology-box-cta" href="methodology.html">See Full Methodology &rarr;</a>
  </div>
</div>

<div class="footer">
  <div class="footer-inner">
    <div class="footer-left">
      <span class="footer-logo">Powered by NOAH</span>
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
    arena_preds = pdata.get("arena_predictions", {})
    pillar_delta = pdata.get("_delta")

    # Score colour and arrow based on delta
    if pillar_delta is not None and pillar_delta > 0:
        hero_score_color = "var(--green)"
        hero_score_arrow = ' <span style="font-size:0.45em;vertical-align:middle">&#9650;</span>'
    elif pillar_delta is not None and pillar_delta < 0:
        hero_score_color = "var(--red)"
        hero_score_arrow = ' <span style="font-size:0.45em;vertical-align:middle">&#9660;</span>'
    else:
        hero_score_color = "var(--green)" if isinstance(score, int) and score >= 50 else "var(--red)" if isinstance(score, int) else "white"
        hero_score_arrow = ""

    # Title — clean white, no highlight colour
    title_html = html.escape(pillar["name"])

    # Build pillar navigation menu
    pillar_nav_items = ""
    for pk, pv in PILLARS.items():
        active = ' class="pnav-active"' if pk == key else ""
        report_file = f"uk-{pk}-{target_date}.html"
        pillar_nav_items += f'<a href="{report_file}"{active}><span class="pnav-num">{pv["pillar_num"]}</span> {html.escape(pv["short"])}</a>\n'

    # Handle missing executive summary
    if not exec_summary or exec_summary.startswith("[Section"):
        exec_summary = "Assessment data not available for this cycle. The intelligence pipeline did not return a structured executive summary for this pillar."

    # Build executive summary HTML — use What/Why/Watch if available (v2.2), else single block
    exec_what = pdata.get("exec_what", "")
    exec_why = pdata.get("exec_why", "")
    exec_watch = pdata.get("exec_watch", "")

    if exec_what or exec_why or exec_watch:
        # v2.2 structured executive summary
        exec_html = ""
        if exec_what:
            exec_html += f'      <div class="exec-sub">\n        <h4 class="exec-sub-head">What is happening</h4>\n        <p>{html.escape(exec_what)}</p>\n      </div>\n'
        if exec_why:
            exec_html += f'      <div class="exec-sub">\n        <h4 class="exec-sub-head">Why it matters</h4>\n        <p>{html.escape(exec_why)}</p>\n      </div>\n'
        if exec_watch:
            exec_html += f'      <div class="exec-sub">\n        <h4 class="exec-sub-head">What to watch</h4>\n        <p>{html.escape(exec_watch)}</p>\n      </div>\n'
    else:
        # Legacy single-block executive summary
        exec_paragraphs = [p.strip() for p in exec_summary.split("\n") if p.strip()]
        exec_html = ""
        for i, para in enumerate(exec_paragraphs):
            weight = ' style="font-weight:600"' if i == 0 else ""
            exec_html += f"      <p{weight}>{html.escape(para)}</p>\n"

    # Extract arena findings (from exec summary text patterns)
    findings = extract_arena_findings(exec_summary, conclusion)

    # Merge with arena_context data for richer metadata
    arena_ctx = pdata.get("arena_context", {})

    # Override findings posture with arena_context posture (more reliable than regex extraction)
    for f in findings:
        ctx = arena_ctx.get(f["arena"], {})
        if ctx.get("posture"):
            f["posture"] = ctx["posture"].capitalize()

    # Supplement findings with any arena_context entries the regex missed
    if arena_ctx:
        found_names = {f["arena"] for f in findings}
        for arena_name, ctx in arena_ctx.items():
            if arena_name not in found_names:
                ap = ctx.get("posture", "")
                if ap.lower() in ("strong",):
                    findings.append({"arena": arena_name, "posture": "Strong", "detail": ""})
                elif ap.lower() in ("weak",):
                    findings.append({"arena": arena_name, "posture": "Weak", "detail": ""})
                elif ap.lower() in ("moderate", "mixed"):
                    findings.append({"arena": arena_name, "posture": "Mixed", "detail": ""})
                elif ap.lower() in ("insufficient data",):
                    findings.append({"arena": arena_name, "posture": "Uncertain", "detail": "Insufficient data"})
                else:
                    findings.append({"arena": arena_name, "posture": "Uncertain", "detail": ap})

    # Compute per-arena average scores from perception dashboard
    # Use sovereign_view if available, else fall back to global_view (v2.2 format)
    perc_dash_raw = pdata.get("perception_dashboard", [])
    arena_sv_scores = {}
    for p in perc_dash_raw:
        a = p.get("arena", "")
        sv = p.get("sovereign_view") if p.get("sovereign_view") is not None else p.get("global_view")
        if a and sv is not None:
            arena_sv_scores.setdefault(a, []).append(sv)
    arena_avg_scores = {a: round(sum(vs) / len(vs)) for a, vs in arena_sv_scores.items() if vs}

    # Build arena strip — horizontal bar of arena gauges under the hero (matches dashboard scoreboard)
    arena_strip_html = ""
    for name, ctx in arena_ctx.items():
        ap = ctx.get("posture", "Mixed")
        momentum = ctx.get("momentum", "Stable")
        # Get numeric score for this arena (average sovereign view)
        arena_score = arena_avg_scores.get(name)
        if arena_score is None:
            # Try fuzzy match
            for k, v in arena_avg_scores.items():
                if k.lower() in name.lower() or name.lower() in k.lower():
                    arena_score = v
                    break
        score_display = str(arena_score) if arena_score is not None else "—"

        if ap.lower() in ("strong",):
            p_color = "var(--green)"
        elif ap.lower() in ("weak",):
            p_color = "var(--red)"
        else:
            # Moderate/Mixed/Insufficient — colour by score if available, else green/red by posture hint
            if arena_score is not None:
                p_color = "var(--green)" if arena_score >= 50 else "var(--red)"
            else:
                p_color = "var(--green)" if ap.lower() in ("moderate",) else "var(--red)"

        mom_color = "var(--green)" if momentum.lower() == "rising" else "var(--red)" if momentum.lower() == "fading" else "rgba(255,255,255,0.5)"
        mom_arrow = "&#9650;" if momentum.lower() == "rising" else "&#9660;" if momentum.lower() == "fading" else "&#8594;"

        # Score arrow based on posture
        if ap.lower() in ("strong",):
            ag_arrow = ' <span style="font-size:0.6em">&#9650;</span>'
        elif ap.lower() in ("weak",):
            ag_arrow = ' <span style="font-size:0.6em">&#9660;</span>'
        elif arena_score is not None:
            ag_arrow = ' <span style="font-size:0.6em">&#9650;</span>' if arena_score >= 50 else ' <span style="font-size:0.6em">&#9660;</span>'
        else:
            ag_arrow = ""

        arena_strip_html += f'''
        <div class="arena-gauge">
          <div class="arena-gauge-name">{html.escape(name).upper()}</div>
          <div class="arena-gauge-score" style="color:{p_color}">{score_display}{ag_arrow}</div>
          <div class="arena-gauge-posture">{html.escape(ap).upper()}</div>
          <div class="arena-gauge-momentum" style="color:{mom_color}">{mom_arrow} {html.escape(momentum)}</div>
        </div>'''

    # Build key statistics row
    arena_count = len(arena_ctx) or len(findings)
    strong_count_f = sum(1 for f in findings if f["posture"] == "Strong")
    weak_count_f = sum(1 for f in findings if f["posture"] == "Weak")
    stats_html = f'''
      <div class="key-stats">
        <div class="key-stat">
          <div class="key-stat-num" style="color:var(--pillar)">{arena_count}</div>
          <div class="key-stat-label">Arenas Assessed</div>
        </div>
        <div class="key-stat">
          <div class="key-stat-num" style="color:var(--green)">{strong_count_f}</div>
          <div class="key-stat-label">Arenas Strong</div>
        </div>
        <div class="key-stat">
          <div class="key-stat-num" style="color:var(--red)">{weak_count_f}</div>
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
          <div class="key-stat-label">Trends Monitored</div>
        </div>
      </div>'''

    # Build perception dashboard table — arena-grouped (v2.2)
    perc_dash = pdata.get("perception_dashboard", [])
    perception_html = ""
    if perc_dash:
        # Check if data is already arena-grouped from parser (v2.2 format)
        already_grouped = any(p.get("is_arena_summary") for p in perc_dash)

        rows = ""
        if already_grouped:
            # Data already has arena summary and proposition rows — render directly
            for p in perc_dash:
                sv = p.get("sovereign_view") if p.get("sovereign_view") is not None else p.get("global_view")
                sv_str = f"{sv}%" if sv is not None else "—"
                sv_style = ""
                if sv is not None:
                    sv_color = "var(--green)" if sv >= 50 else "var(--red)"
                    sv_arrow = "&#9650;" if sv >= 50 else "&#9660;"
                    sv_str = f"{sv}% <span style='font-size:0.7em'>{sv_arrow}</span>"
                    sv_style = f' style="color:{sv_color};font-weight:{"800" if p.get("is_arena_summary") else "700"}"'
                conf = p.get("signal_strength", "") or p.get("confidence", "")
                conf_cls = "conf-medium" if conf.lower() == "medium" else "conf-low" if conf.lower() in ("low", "thin") else "conf-high"
                prop_emerging = p.get("emerging", "").strip()
                em_str = "&#10003;" if prop_emerging and prop_emerging not in ("—", "-", ",") else "—"

                if p.get("is_arena_summary"):
                    rows += f'''        <tr class="pd-arena-row">
          <td class="pd-arena-name"><strong>{html.escape(p.get("proposition", ""))}</strong></td>
          <td class="pd-pct"{sv_style}>{sv_str}</td>
          <td><span class="conf-badge {conf_cls}">{html.escape(conf)}</span></td>
          <td class="pd-emerging">{em_str}</td>
        </tr>\n'''
                else:
                    rows += f'''        <tr class="pd-prop-row">
          <td class="pd-prop"><span class="pd-indent">&lfloor;</span> {html.escape(p.get("proposition", ""))}</td>
          <td class="pd-pct"{sv_style}>{sv_str}</td>
          <td><span class="conf-badge {conf_cls}">{html.escape(conf)}</span></td>
          <td class="pd-emerging">{em_str}</td>
        </tr>\n'''
        else:
            # Legacy format — group by arena and compute summaries
            arena_groups = {}
            for p in perc_dash:
                arena = p.get("arena", "Unassigned")
                arena_groups.setdefault(arena, []).append(p)

            for arena_name, props in arena_groups.items():
                arena_scores_list = []
                for p in props:
                    sv = p.get("sovereign_view") if p.get("sovereign_view") is not None else p.get("global_view")
                    if sv is not None:
                        arena_scores_list.append(sv)
                arena_avg = round(sum(arena_scores_list) / len(arena_scores_list)) if arena_scores_list else None
                if arena_avg is not None:
                    a_color = "var(--green)" if arena_avg >= 50 else "var(--red)"
                    a_arrow = "&#9650;" if arena_avg >= 50 else "&#9660;"
                    a_str = f"{arena_avg}% <span style='font-size:0.7em'>{a_arrow}</span>"
                    a_style = f' style="color:{a_color};font-weight:800"'
                else:
                    a_str = "—"
                    a_style = ""
                strengths = [p.get("signal_strength", "") for p in props if p.get("signal_strength")]
                arena_signal = max(set(strengths), key=strengths.count) if strengths else "—"
                arena_signal_cls = "conf-medium" if arena_signal.lower() == "medium" else "conf-low" if arena_signal.lower() in ("low", "thin") else "conf-high"
                has_emerging = any(p.get("emerging", "").strip() not in ("", "—", "-") for p in props)
                emerging_str = "&#10003;" if has_emerging else "—"

                rows += f'''        <tr class="pd-arena-row">
          <td class="pd-arena-name"><strong>{html.escape(arena_name)}</strong></td>
          <td class="pd-pct"{a_style}>{a_str}</td>
          <td><span class="conf-badge {arena_signal_cls}">{html.escape(arena_signal)}</span></td>
          <td class="pd-emerging">{emerging_str}</td>
        </tr>\n'''
                for p in props:
                    sv = p.get("sovereign_view") if p.get("sovereign_view") is not None else p.get("global_view")
                    sv_str = f"{sv}%" if sv is not None else "—"
                    sv_style = ""
                    if sv is not None:
                        sv_color = "var(--green)" if sv >= 50 else "var(--red)"
                        sv_arrow = "&#9650;" if sv >= 50 else "&#9660;"
                        sv_str = f"{sv}% <span style='font-size:0.7em'>{sv_arrow}</span>"
                        sv_style = f' style="color:{sv_color};font-weight:700"'
                    conf = p.get("signal_strength", "") or p.get("confidence", "")
                    conf_cls = "conf-medium" if conf.lower() == "medium" else "conf-low" if conf.lower() in ("low", "thin") else "conf-high"
                    prop_emerging = p.get("emerging", "").strip()
                    prop_emerging_str = "&#10003;" if prop_emerging and prop_emerging not in ("—", "-") else "—"
                    rows += f'''        <tr class="pd-prop-row">
          <td class="pd-prop"><span class="pd-indent">&lfloor;</span> {html.escape(p.get("proposition", ""))}</td>
          <td class="pd-pct"{sv_style}>{sv_str}</td>
          <td><span class="conf-badge {conf_cls}">{html.escape(conf)}</span></td>
          <td class="pd-emerging">{prop_emerging_str}</td>
        </tr>\n'''

        perception_html = f'''
      <div class="table-scroll">
      <table class="pd-table">
        <thead><tr><th>Arena / Proposition</th><th>External Perception</th><th>Signal Strength</th><th>Emerging</th></tr></thead>
        <tbody>
{rows}        </tbody>
      </table>
      </div>
      <p class="pd-footnote">External perception reflects monitoring of 1.6 million sources across global media, government communications, and specialist publications.</p>'''

    # Build Standing Context — unified per-arena cards with inline strength/vulnerability signals
    strength_details = pdata.get("strength_signal_details", [])
    vuln_details = pdata.get("vuln_signal_details", [])

    # Index signals by arena for inline rendering
    strength_by_arena = {}
    for s in strength_details:
        a = s.get("arena", "Unassigned")
        strength_by_arena.setdefault(a, []).append(s)
    vuln_by_arena = {}
    for v in vuln_details:
        a = v.get("arena", "Unassigned")
        vuln_by_arena.setdefault(a, []).append(v)

    standing_context_html = ""
    for name, ctx in arena_ctx.items():
        ap = ctx.get("posture", "")
        if ap.lower() in ("strong",):
            border_color = "var(--green)"
            badge_bg = "rgba(46,155,110,0.1)"
            badge_color = "#166534"
        elif ap.lower() in ("weak",):
            border_color = "var(--red)"
            badge_bg = "rgba(217,64,72,0.1)"
            badge_color = "#991b1b"
        elif ap.lower() in ("moderate", "mixed"):
            border_color = "var(--amber)"
            badge_bg = "rgba(196,146,10,0.1)"
            badge_color = "#92400e"
        elif ap.lower() in ("insufficient data",):
            border_color = "#999"
            badge_bg = "rgba(120,120,120,0.08)"
            badge_color = "#666"
            ap = "Insufficient Data"
        else:
            border_color = "var(--text-muted)"
            badge_bg = "var(--bg)"
            badge_color = "var(--text-muted)"

        momentum = ctx.get("momentum", "")
        discourse = ctx.get("discourse", "")
        geographies = ctx.get("geographies", "")
        verified = ctx.get("spot_checked_trends", "0")
        echo_risk = ctx.get("echo_risk", "No")
        articles = ctx.get("articles_count", "")
        summary_text = ctx.get("summary", "")

        mom_color = "var(--green)" if momentum.lower() == "rising" else "var(--red)" if momentum.lower() == "fading" else "var(--text-mid)"

        # Arena metadata grid — adaptive based on available fields
        meta_fields = [
            ("Active trends", str(verified), ""),
        ]
        if articles:
            meta_fields.append(("Articles", str(articles), ""))
        meta_fields.append(("Momentum", momentum, f'style="color:{mom_color}"'))
        meta_fields.append(("Discourse", discourse.replace("public commentary is ", "").title(), ""))
        meta_fields.append(("Echo risk", echo_risk, ""))

        meta_cells = ""
        for label, val, style_attr in meta_fields:
            if val:
                meta_cells += f'<div class="arena-card-field"><span class="arena-field-label">{label}</span><span class="arena-field-val" {style_attr}>{html.escape(val)}</span></div>\n'
        meta_html = f'''
          <div class="arena-card-grid">
            {meta_cells}
          </div>'''

        # Arena narrative summary
        narrative_html = ""
        if summary_text:
            narrative_html = f'<p class="arena-narrative">{html.escape(_fix_emdashes(summary_text))}</p>'

        # Geographies
        geo_html = f'<div class="arena-card-geo"><span class="arena-field-label">Top geographies:</span> {html.escape(geographies)}</div>' if geographies else ""

        # Inline strength signals — "Reinforcing this standing"
        arena_strengths = strength_by_arena.get(name, [])
        # Also fuzzy match
        if not arena_strengths:
            for a_key, s_list in strength_by_arena.items():
                if a_key.lower() in name.lower() or name.lower() in a_key.lower():
                    arena_strengths = s_list
                    break
        reinforcing_html = ""
        if arena_strengths:
            items = ""
            for s in arena_strengths:
                character = s.get("character", "")
                desc = s.get("description", "")
                horizon = s.get("horizon", "")
                items += f'<li><strong>{html.escape(character)}:</strong> {html.escape(desc)}'
                if horizon:
                    items += f' <span class="signal-horizon-tag">{html.escape(horizon)}</span>'
                items += '</li>\n'
            reinforcing_html = f'''
          <div class="standing-signals standing-signals-strength">
            <h5 class="standing-signal-head"><span class="ss-icon ss-icon-strength">&#9650;</span> Reinforcing this standing</h5>
            <ul>{items}</ul>
          </div>'''

        # Inline vulnerability signals — "Pressure on this standing"
        arena_vulns = vuln_by_arena.get(name, [])
        if not arena_vulns:
            for a_key, v_list in vuln_by_arena.items():
                if a_key.lower() in name.lower() or name.lower() in a_key.lower():
                    arena_vulns = v_list
                    break
        pressure_html = ""
        if arena_vulns:
            items = ""
            for v in arena_vulns:
                severity = v.get("severity", "")
                horizon = v.get("horizon", "")
                desc = v.get("description", "")
                sev_cls = "sev-tag-high" if "high" in severity.lower() else "sev-tag-medium" if "medium" in severity.lower() else "sev-tag-low"
                items += f'<li><span class="sev-tag {sev_cls}">{html.escape(severity).upper()}</span> '
                if horizon:
                    items += f'<span class="signal-horizon-tag">{html.escape(horizon)}</span> '
                items += f'{html.escape(desc)}</li>\n'
            pressure_html = f'''
          <div class="standing-signals standing-signals-vuln">
            <h5 class="standing-signal-head"><span class="ss-icon ss-icon-vuln">&#9660;</span> Pressure on this standing</h5>
            <ul>{items}</ul>
          </div>'''

        # Arena micro-outlook (conditional)
        outlook_html_arena = ""
        if arena_preds.get(name, {}).get("has_outlook"):
            outlook_html_arena = f'<div class="arena-outlook">{html.escape(_fix_emdashes(arena_preds[name]["outlook_sentence"]))}</div>'

        standing_context_html += f'''
        <div class="standing-arena-card" style="border-top:3px solid {border_color}">
          <div class="arena-card-header">
            <div class="arena-card-name">{html.escape(name)}</div>
            <span class="arena-badge" style="background:{badge_bg};color:{badge_color}">{html.escape(ap).upper()}</span>
          </div>
          {meta_html}
          {narrative_html}
          {geo_html}
          {reinforcing_html}
          {pressure_html}
          {outlook_html_arena}
        </div>'''

    # Build standing overview table
    standing_overview = pdata.get("standing_overview", [])
    overview_html = ""
    if standing_overview:
        rows = ""
        for o in standing_overview:
            rows += f'        <tr><td class="ov-dim">{html.escape(o.get("dimension", ""))}</td><td class="ov-assess">{html.escape(o.get("assessment", ""))}</td><td>{html.escape(o.get("driver", ""))}</td></tr>\n'
        overview_html = f'''
      <div class="table-scroll">
      <table class="overview-table">
        <thead><tr><th>Dimension</th><th>Assessment</th><th>What Drives It</th></tr></thead>
        <tbody>
{rows}        </tbody>
      </table>
      </div>'''

    # Build priorities section — risk/opportunity framing (v2.2)
    priorities = pdata.get("priorities", [])
    priorities_html = ""
    if priorities:
        current_horizon = ""
        for p in priorities:
            h = p.get("horizon", "Unspecified")
            # Normalise horizon labels for risk/opportunity framing
            horizon_label = h
            h_lower = h.lower()
            if "near" in h_lower or "immediate" in h_lower:
                horizon_label = "Near-term risks and opportunities"
            elif "medium" in h_lower:
                horizon_label = "Medium-term risks and opportunities"
            elif "long" in h_lower:
                horizon_label = "Long-term risks and opportunities"

            if horizon_label != current_horizon:
                if current_horizon:
                    priorities_html += "    </div>\n"
                current_horizon = horizon_label
                priorities_html += f'    <h4 class="priority-horizon">{html.escape(current_horizon)}</h4>\n    <div class="priority-group">\n'

            action = p.get("action", "")
            desc = p.get("description", "")
            arena = p.get("arena", "")

            # Determine if this is a risk or opportunity
            action_lower = action.lower().strip()
            # v2.2 format: action is directly "Risk", "Opportunity", or "Watch"
            if action_lower == "risk":
                risk_type = "Risk"
                risk_cls = "pri-risk"
            elif action_lower == "opportunity":
                risk_type = "Opportunity"
                risk_cls = "pri-opportunity"
            elif action_lower == "watch":
                risk_type = "Watch"
                risk_cls = "pri-watch"
            # Old format: action is a verb like "Address", "Reinforce", "Monitor"
            elif any(w in action_lower for w in ("address", "correct", "structural_response", "mitigate")):
                risk_type = "Risk"
                risk_cls = "pri-risk"
            elif any(w in action_lower for w in ("reinforce", "build", "leverage", "capitalise")):
                risk_type = "Opportunity"
                risk_cls = "pri-opportunity"
            elif "monitor" in action_lower:
                risk_type = "Watch"
                risk_cls = "pri-watch"
            else:
                risk_type = "Risk" if "vuln" in desc.lower() or "weak" in desc.lower() else "Opportunity"
                risk_cls = "pri-risk" if risk_type == "Risk" else "pri-opportunity"

            # Map action to recommended response framing
            if "monitor" in action_lower:
                response = f"Track {html.escape(arena)} for escalation signals."
            elif "reinforce" in action_lower:
                response = f"Proactively reinforce {html.escape(arena)} positioning before adverse framing erodes position."
            elif "correct" in action_lower or "address" in action_lower:
                response = f"Develop counter-narrative or corrective positioning to address adverse framing in {html.escape(arena)}."
            elif "structural" in action_lower:
                response = f"Structural response required in {html.escape(arena)} to address root cause."
            else:
                response = ""

            priorities_html += f'''      <div class="priority-item priority-item-{risk_cls}">
        <div class="priority-type-row">
          <span class="priority-type {risk_cls}">{risk_type}</span>
          {('<span class="priority-arena-tag">' + html.escape(arena) + '</span>') if arena else ''}
        </div>
        <p class="priority-desc">{html.escape(desc)}</p>
        {('<p class="priority-response"><strong>Recommended response:</strong> ' + response + '</p>') if response else ''}
      </div>\n'''
        if current_horizon:
            priorities_html += "    </div>\n"

    # Build conclusion
    conclusion_html = ""
    if conclusion and not conclusion.startswith("[Section"):
        conclusion_paras = [p.strip() for p in conclusion.split("\n") if p.strip()]
        for para in conclusion_paras:
            # Skip "Standing posture this cycle: X" lines — the template adds its own badge
            if re.match(r"^Standing posture this cycle\s*[:\s]", para, re.IGNORECASE):
                continue
            conclusion_html += f"      <p>{html.escape(_fix_emdashes(para))}</p>\n"
    else:
        conclusion_html = "      <p>Standing assessment data will populate when available.</p>\n"

    # Build Forward Outlook / Predictions section
    predictions = pdata.get("predictions", [])
    outlook_html = ""
    if predictions:
        # Sort by probability descending
        sorted_preds = sorted(predictions, key=lambda p: p.get("probability") or 0, reverse=True)
        tiles_html = ""
        for pred in sorted_preds[:10]:  # Max 10 tiles
            prob = pred.get("probability")
            prob_str = str(prob) + "% probability" if prob is not None else "?"
            title = pred.get("title", "")
            horizon = pred.get("horizon", "")
            direction = pred.get("direction", "")
            trigger = pred.get("trigger", "")
            signal = pred.get("signal_strength", "")
            pred_type = pred.get("type", "")

            # Type badge class (may be empty in v2.2 format)
            type_lower = pred_type.lower()
            type_cls = "pred-type-vuln" if "vuln" in type_lower else "pred-type-strength"

            # Direction badge class
            dir_lower = direction.lower()
            if "intensif" in dir_lower:
                dir_cls = "pred-dir-intensifying"
            elif "fading" in dir_lower:
                dir_cls = "pred-dir-fading"
            elif "revers" in dir_lower:
                dir_cls = "pred-dir-reversing"
            else:
                dir_cls = "pred-dir-stable"

            # Tile border colour: use type if available, else direction
            if pred_type:
                border_color = "var(--red)" if "vuln" in type_lower else "var(--green)"
            elif "fading" in dir_lower or "revers" in dir_lower:
                border_color = "var(--red)"
            else:
                border_color = "var(--green)"

            # Type badge only shown when type is present
            type_badge = f'<span class="pred-badge {type_cls}">{html.escape(pred_type.upper())}</span>' if pred_type else ''

            tiles_html += f'''
        <div class="pred-tile" style="border-left: 3px solid {border_color}">
          <div class="pred-prob">{html.escape(prob_str)}</div>
          <div class="pred-title">{html.escape(title)}</div>
          <div class="pred-badges">
            {type_badge}
            <span class="pred-badge {dir_cls}">{html.escape(direction.upper())}</span>
            {('<span class="pred-badge pred-signal-strong">' + html.escape(signal.upper()) + '</span>') if signal else ''}
            <span class="pred-badge pred-horizon">{html.escape(horizon.upper())}</span>
          </div>
          {('<div class="pred-trigger"><strong>What would change it:</strong> ' + html.escape(_fix_emdashes(trigger)) + '</div>') if trigger else ''}
        </div>'''

        pred_count = len(sorted_preds)
        dominant = ""
        dirs = [p.get("direction", "").lower() for p in sorted_preds if p.get("direction")]
        if dirs:
            from collections import Counter
            dominant = Counter(dirs).most_common(1)[0][0].title()
        summary_line = f"Outlook: {pred_count} signals assessed"
        if dominant:
            summary_line += f", dominant direction {dominant}"
        # Count intensifying arenas
        intensifying_count = sum(1 for d in dirs if "intensif" in d)
        if intensifying_count:
            summary_line += f". {intensifying_count} arenas show intensifying predictions."

        outlook_html = f'''
      <div class="pred-grid">{tiles_html}
      </div>
      <div class="pred-summary">{summary_line}</div>'''
    else:
        outlook_html = '''
      <div class="exec-card">
        <p>Prediction depth limited this cycle &mdash; signal strength insufficient for forward outlook on current trends.</p>
      </div>'''

    # ─── Section 5: Sovereign Profile Snapshot ───
    profile_snapshot = pdata.get("profile_snapshot", {})
    profile_html = ""
    if profile_snapshot:
        for sub_title, rows in profile_snapshot.items():
            profile_html += f'<h4 class="profile-sub-title">{html.escape(sub_title)}</h4>\n'
            profile_html += '<table class="profile-table"><tbody>\n'
            for row in rows:
                field = html.escape(_fix_emdashes(row.get("field", "")))
                detail = html.escape(_fix_emdashes(row.get("detail", "")))
                profile_html += f'<tr><td class="profile-field">{field}</td><td class="profile-detail">{detail}</td></tr>\n'
            profile_html += '</tbody></table>\n'
    profile_section_html = f'''
  <div class="sec">
    <div class="sec-head">
      <h2 class="sec-title">Sovereign Profile Snapshot</h2>
      <span class="sec-num">Section 05</span>
    </div>
    <div class="exec-card">
      {profile_html if profile_html else '<p>Profile snapshot not available this cycle.</p>'}
    </div>
  </div>''' if profile_snapshot else ''

    # ─── Section 9: Structural Contradictions ───
    contradictions_text = pdata.get("structural_contradictions", "")
    contradictions_section_html = ""
    if contradictions_text:
        contradictions_section_html = f'''
  <div class="sec">
    <div class="sec-head">
      <h2 class="sec-title">Structural Contradictions</h2>
      <span class="sec-num">Section 09</span>
    </div>
    <div class="exec-card">
      <p>{html.escape(_fix_emdashes(contradictions_text))}</p>
    </div>
  </div>'''

    # ─── Section 10: Standing Diagnostic Coverage ───
    diagnostic_rows = pdata.get("diagnostic_coverage", [])
    diagnostic_html = ""
    if diagnostic_rows:
        diagnostic_html += '<table class="diag-table"><thead><tr><th>Diagnostic prompt</th><th>Coverage</th><th>What is clear</th><th>What remains bounded</th></tr></thead><tbody>\n'
        for dr in diagnostic_rows:
            prompt = html.escape(_fix_emdashes(dr.get("prompt", "")))
            coverage = dr.get("coverage", "")
            cov_cls = "diag-covered" if "managed" in coverage.lower() else "diag-not-covered" if "not covered" in coverage.lower() else ""
            clear = html.escape(_fix_emdashes(dr.get("clear", "")))
            bounded = html.escape(_fix_emdashes(dr.get("bounded", "")))
            diagnostic_html += f'<tr><td class="diag-prompt">{prompt}</td><td class="diag-coverage {cov_cls}">{html.escape(coverage)}</td><td>{clear}</td><td>{bounded}</td></tr>\n'
        diagnostic_html += '</tbody></table>\n'
    diagnostic_section_html = f'''
  <div class="sec">
    <div class="sec-head">
      <h2 class="sec-title">Standing Diagnostic Coverage</h2>
      <span class="sec-num">Section 10</span>
    </div>
    <div class="exec-card">
      {diagnostic_html if diagnostic_html else '<p>Diagnostic coverage data not available this cycle.</p>'}
    </div>
  </div>''' if diagnostic_rows else ''

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
<meta property="og:image" content="https://ivanmassow.github.io/client-reports/sovereign-signal/og-card.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:type" content="article">
<meta property="og:url" content="https://ivanmassow.github.io/client-reports/sovereign-signal/uk-{key}-{target_date}.html">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{html.escape(headline)}">
<meta name="twitter:image" content="https://ivanmassow.github.io/client-reports/sovereign-signal/og-card.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Lora:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root {{
  --slate: #1a1e27; --slate-deep: #1a1e27; --slate-mid: #2e323c;
  --accent: #C9A84C; --accent-light: #EDE0B8;
  --red: #E53E3E; --green: #22C55E; --amber: #C4920A;
  --text: #2C2C2C; --text-mid: #555B66; --text-muted: #8A8F98;
  --bg: #FAFAF8; --bg-card: #FFFFFF; --border: #E8E6E1; --border-light: #F2F0EB;
  --pillar: {pillar['color']}; --pillar-light: {pillar['color_light']}; --pillar-mid: {pillar['color_mid']};
  --card-radius: 8px; --card-shadow: 0 1px 3px rgba(0,0,0,0.04);
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; color: var(--text); background: var(--bg); -webkit-font-smoothing: antialiased; line-height: 1.6; }}

/* Topbar */
.topbar {{ background: var(--slate); display: flex; align-items: center; justify-content: space-between; padding: 0 32px; height: 52px; position: sticky; top: 0; z-index: 100; box-shadow: 0 1px 0 0 var(--slate); }}
.topbar-left {{ display: flex; align-items: center; gap: 14px; }}
.topbar-logo {{ font-family: 'Montserrat', sans-serif; font-weight: 700; font-size: 16px; letter-spacing: 0.06em; color: rgba(255,255,255,0.9); text-transform: uppercase; }}
.topbar-divider {{ width: 1px; height: 20px; background: rgba(255,255,255,0.12); }}
.topbar-brand {{ font-size: 11px; font-weight: 500; letter-spacing: 1.5px; text-transform: uppercase; color: rgba(255,255,255,0.6); }}
.topbar-right {{ display: flex; align-items: center; gap: 20px; }}
.topbar-date {{ font-size: 11px; color: rgba(255,255,255,0.55); }}
.back-link {{ font-size: 11px; font-weight: 500; color: rgba(255,255,255,0.45); text-decoration: none; padding: 6px 12px; border-radius: 4px; transition: all 0.15s; }}

/* Pillar Navigation */
.pillar-nav {{ display: flex; align-items: center; gap: 2px; }}
.pillar-nav a {{ font-family: 'Montserrat', sans-serif; font-size: 9px; font-weight: 500; color: rgba(255,255,255,0.35); text-decoration: none; padding: 4px 8px; border-radius: 3px; transition: all 0.15s; letter-spacing: 0.5px; white-space: nowrap; }}
.pillar-nav a:hover {{ color: rgba(255,255,255,0.7); background: rgba(255,255,255,0.06); }}
.pillar-nav a.pnav-active {{ color: #fff; background: rgba(255,255,255,0.1); }}
.pnav-num {{ font-size: 8px; font-weight: 700; opacity: 0.5; margin-right: 3px; }}
.pillar-nav a.pnav-active .pnav-num {{ opacity: 0.8; }}
.back-link:hover {{ color: #fff; background: rgba(255,255,255,0.08); }}

/* Hero */
.hero {{ background: var(--slate-deep); position: relative; overflow: hidden; margin-top: -1px; }}
.hero-bg {{ position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: url('union-flag.png') center center / cover no-repeat; opacity: 0.5; filter: saturate(0.6) contrast(1.05); }}
.hero::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: linear-gradient(105deg, rgba(26,30,39,0.92) 0%, rgba(26,30,39,0.85) 22%, rgba(26,30,39,0.55) 48%, rgba(26,30,39,0.25) 72%, rgba(26,30,39,0.12) 100%); z-index: 1; pointer-events: none; }}
.hero::after {{ content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 1px; background: rgba(255,255,255,0.08); z-index: 3; }}
.hero-inner {{ max-width: 1200px; margin: 0 auto; position: relative; z-index: 2; display: flex; align-items: flex-start; justify-content: space-between; padding: 60px 32px 0; min-height: 395px; }}
.hero-left {{ flex: 1; max-width: 540px; padding-top: 12px; }}
.hero-tag {{ font-size: 9px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; padding: 3px 10px; border-radius: 4px; background: var(--pillar-light); color: var(--pillar); display: inline-block; margin-bottom: 14px; }}
.hero-title {{ font-family: 'Lora', Georgia, serif; font-size: 42px; font-weight: 700; color: rgba(255,255,255,0.92); line-height: 1.12; margin-bottom: 12px; }}
.hero-meta {{ font-size: 12px; color: rgba(255,255,255,0.55); letter-spacing: 1px; margin-bottom: 20px; }}
.hero-desc {{ font-family: 'Lora', Georgia, serif; font-size: 14px; color: rgba(255,255,255,0.55); max-width: 440px; line-height: 1.7; }}
.score-block {{ width: 220px; flex-shrink: 0; margin-top: 8px; }}
.score-block-inner {{ background: rgba(26,30,39,0.45); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px 20px 20px; text-align: center; }}
.score-block-label {{ font-size: 9px; font-weight: 600; letter-spacing: 2px; text-transform: uppercase; color: rgba(255,255,255,0.55); margin-bottom: 6px; }}
.score-block-num {{ font-family: 'Montserrat', sans-serif; font-size: 64px; font-weight: 800; color: white; line-height: 1; }}
.score-block-max {{ font-size: 11px; color: rgba(255,255,255,0.45); margin-top: 4px; margin-bottom: 12px; }}
.posture {{ display: inline-flex; align-items: center; gap: 6px; font-size: 10px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; padding: 4px 14px; border-radius: 4px; }}
.posture-mixed {{ color: var(--amber); background: rgba(196,146,10,0.12); }}
.posture-strong {{ color: var(--green); background: rgba(46,155,110,0.12); }}
.posture-weak {{ color: var(--red); background: rgba(217,64,72,0.12); }}
.posture-stable {{ color: var(--green); background: rgba(46,155,110,0.08); }}

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

/* Arena Strip — gauges below hero on white */
.arena-strip {{ display: flex; flex-wrap: wrap; justify-content: center; background: var(--bg); position: relative; z-index: 3; border-bottom: 1px solid var(--border); }}
.arena-gauge {{ flex: 1; min-width: 120px; max-width: 220px; padding: 20px 12px 18px; text-align: center; border-right: 1px solid var(--border-light); }}
.arena-gauge:last-child {{ border-right: none; }}
.arena-gauge-name {{ font-size: 9px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; color: var(--text); margin-bottom: 10px; line-height: 1.3; min-height: 36px; display: flex; align-items: flex-end; justify-content: center; text-align: center; }}
.arena-gauge-score {{ font-family: 'Montserrat', sans-serif; font-size: 34px; font-weight: 800; line-height: 1; margin-bottom: 6px; }}
.arena-gauge-posture {{ font-size: 9px; font-weight: 600; letter-spacing: 0.5px; color: var(--text-muted); margin-bottom: 4px; }}
.arena-gauge-momentum {{ font-size: 10px; color: var(--text-mid); }}

/* Arena Cards */
.arena-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }}
.arena-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--card-radius); padding: 0; box-shadow: var(--card-shadow); overflow: hidden; }}
.arena-card-header {{ display: flex; align-items: center; justify-content: space-between; padding: 14px 18px 10px; }}
.arena-card-name {{ font-size: 14px; font-weight: 600; color: var(--text); }}
.arena-badge {{ font-size: 9px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; padding: 3px 10px; border-radius: 10px; flex-shrink: 0; }}
.arena-card-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: var(--border-light); padding: 0; }}
.arena-card-field {{ background: var(--bg-card); padding: 8px 18px; }}
.arena-field-label {{ font-size: 9px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; color: var(--text-muted); display: block; margin-bottom: 2px; }}
.arena-field-val {{ font-size: 12px; font-weight: 600; color: var(--text); }}
.arena-card-geo {{ padding: 8px 18px 12px; font-size: 11px; color: var(--text-muted); border-top: 1px solid var(--border-light); }}

/* Perception Dashboard Table */
.table-scroll {{ overflow-x: auto; -webkit-overflow-scrolling: touch; border-radius: var(--card-radius); }}
.pd-table {{ width: 100%; min-width: 540px; border-collapse: collapse; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--card-radius); overflow: hidden; box-shadow: var(--card-shadow); }}
.pd-table thead th {{ font-size: 10px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; color: var(--text-muted); padding: 12px 16px; text-align: left; border-bottom: 2px solid var(--border); background: var(--bg); }}
.pd-table th:nth-child(2), .pd-table td:nth-child(2) {{ text-align: center; width: 120px; }}
.pd-table th:nth-child(3), .pd-table td:nth-child(3) {{ text-align: center; width: 120px; }}
.pd-table th:nth-child(4), .pd-table td:nth-child(4) {{ width: 150px; }}
.pd-table tbody td {{ font-size: 13px; color: var(--text-mid); padding: 12px 16px; border-bottom: 1px solid var(--border-light); vertical-align: top; }}
.pd-table tbody tr:last-child td {{ border-bottom: none; }}
.pd-prop {{ width: 50%; min-width: 280px; line-height: 1.5; }}
.pd-pct {{ font-family: 'Montserrat', sans-serif; font-weight: 700; font-size: 14px; white-space: nowrap; width: 90px; text-align: center; }}
.pd-arena {{ font-size: 11px; color: var(--text-muted); white-space: nowrap; }}
.conf-badge {{ font-size: 9px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; padding: 3px 10px; border-radius: 10px; white-space: nowrap; }}
.conf-high {{ background: rgba(46,155,110,0.1); color: #166534; }}
.conf-medium {{ background: rgba(146,64,14,0.1); color: #92400e; }}
.conf-low {{ background: var(--bg); color: var(--text-muted); border: 1px solid var(--border); }}

/* Signal Cards */
.signal-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--card-radius); padding: 20px 24px; box-shadow: var(--card-shadow); margin-bottom: 12px; }}
.signal-card-strength {{ border-left: 4px solid var(--green); }}
.signal-card-vuln {{ border-left: 4px solid var(--red); }}
.signal-card-header {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }}
.signal-card-id {{ font-family: 'Montserrat', sans-serif; font-weight: 800; font-size: 14px; color: var(--text); padding: 4px 12px; background: var(--bg); border: 1px solid var(--border); border-radius: 4px; }}
.signal-badge {{ font-size: 9px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; padding: 3px 10px; border-radius: 10px; }}
.signal-badge-strength {{ background: rgba(46,155,110,0.12); color: #166534; }}
.signal-badge-vuln {{ background: rgba(217,64,72,0.12); color: #991b1b; }}
.signal-badge-arena {{ background: var(--bg); color: var(--text-mid); border: 1px solid var(--border); }}
.signal-badge-horizon {{ background: var(--bg); color: var(--text-mid); border: 1px solid var(--border); }}
.char-reputational {{ background: rgba(196,146,10,0.1); color: #92400e; }}
.char-structural {{ background: rgba(46,155,110,0.1); color: #166534; }}
.char-strategic {{ background: rgba(88,64,14,0.08); color: #553f0e; }}
.char-policy {{ background: rgba(146,64,14,0.1); color: #92400e; }}
.sev-high {{ background: rgba(217,64,72,0.12); color: #991b1b; }}
.sev-medium {{ background: rgba(196,146,10,0.1); color: #92400e; }}
.sev-low {{ background: var(--bg); color: var(--text-muted); border: 1px solid var(--border); }}
.signal-card-title {{ font-family: 'Lora', Georgia, serif; font-size: 15px; font-weight: 600; color: var(--text); margin-bottom: 8px; }}
.signal-card-desc {{ font-size: 13px; color: var(--text-mid); line-height: 1.7; margin-bottom: 10px; }}
.signal-card-meta {{ display: flex; gap: 16px; flex-wrap: wrap; font-size: 11px; color: var(--text-muted); }}

/* Standing Overview Table */
.overview-table {{ width: 100%; min-width: 580px; border-collapse: collapse; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--card-radius); overflow: hidden; box-shadow: var(--card-shadow); }}
.overview-table thead th {{ font-size: 10px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; color: var(--text-muted); padding: 12px 16px; text-align: left; border-bottom: 2px solid var(--border); background: var(--bg); }}
.overview-table tbody td {{ font-size: 13px; color: var(--text-mid); padding: 12px 16px; border-bottom: 1px solid var(--border-light); }}
.overview-table tbody tr:last-child td {{ border-bottom: none; }}
.ov-dim {{ font-weight: 600; color: var(--text); white-space: nowrap; }}
.ov-assess {{ font-weight: 700; white-space: nowrap; }}

/* Priorities */
.priority-horizon {{ font-size: 14px; font-weight: 600; color: var(--text); margin: 20px 0 10px; text-transform: capitalize; }}
.priority-group {{ display: flex; flex-direction: column; gap: 8px; }}
.priority-item {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--card-radius); padding: 14px 18px; box-shadow: var(--card-shadow); }}
.priority-action {{ font-size: 9px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; padding: 3px 10px; border-radius: 10px; display: inline-block; margin-bottom: 6px; }}
.pri-address {{ background: rgba(217,64,72,0.12); color: #991b1b; }}
.pri-monitor {{ background: rgba(196,146,10,0.1); color: #92400e; }}
.pri-reinforce {{ background: rgba(46,155,110,0.12); color: #166534; }}
.pri-build {{ background: rgba(46,155,110,0.08); color: #166534; }}
.priority-arena {{ font-size: 11px; font-weight: 600; color: var(--pillar); display: block; margin-bottom: 4px; }}
.priority-desc {{ font-size: 12px; color: var(--text-mid); line-height: 1.6; }}

/* Conclusion card */
.conclusion-card {{ background: var(--bg-card); border: 1px solid var(--border); border-left: 4px solid var(--pillar); padding: 28px 32px; border-radius: var(--card-radius); box-shadow: var(--card-shadow); }}
.conclusion-card p {{ font-family: 'Lora', Georgia, serif; font-size: 14px; color: var(--text-mid); line-height: 1.8; margin-bottom: 14px; }}
.conclusion-card p:last-child {{ margin-bottom: 0; }}
.conclusion-posture {{ display: inline-flex; align-items: center; gap: 8px; margin-top: 16px; font-size: 12px; font-weight: 600; }}
.conclusion-posture-badge {{ font-size: 10px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; padding: 4px 14px; border-radius: 4px; }}

/* Profile Snapshot tables */
.profile-sub-title {{ font-family: 'Montserrat', sans-serif; font-size: 11px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: var(--pillar); margin: 16px 0 8px; }}
.profile-sub-title:first-child {{ margin-top: 0; }}
.profile-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
.profile-table td {{ padding: 6px 12px; border-bottom: 1px solid var(--border-light); vertical-align: top; }}
.profile-field {{ font-weight: 600; color: var(--text); width: 30%; white-space: nowrap; }}
.profile-detail {{ color: var(--text-mid); }}

/* Diagnostic Coverage table */
.diag-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
.diag-table th {{ font-family: 'Montserrat', sans-serif; font-size: 9px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: var(--text-muted); padding: 8px 10px; text-align: left; border-bottom: 2px solid var(--border); }}
.diag-table td {{ padding: 8px 10px; border-bottom: 1px solid var(--border-light); vertical-align: top; color: var(--text-mid); line-height: 1.5; }}
.diag-prompt {{ font-weight: 600; color: var(--text); }}
.diag-covered {{ color: var(--green); font-weight: 600; }}
.diag-not-covered {{ color: var(--red); font-weight: 600; }}

/* Executive Summary — What/Why/Watch sub-blocks */
.exec-sub {{ margin-bottom: 20px; }}
.exec-sub:last-child {{ margin-bottom: 0; }}
.exec-sub-head {{ font-family: 'Montserrat', sans-serif; font-size: 11px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: var(--pillar); margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }}
.exec-sub-head::before {{ content: ''; width: 3px; height: 14px; background: var(--pillar); border-radius: 2px; flex-shrink: 0; }}
.exec-sub p {{ font-family: 'Lora', Georgia, serif; font-size: 14px; color: var(--text-mid); line-height: 1.8; }}

/* Arena-grouped Perception Dashboard */
.pd-arena-row {{ background: var(--bg) !important; }}
.pd-arena-row td {{ border-bottom: 2px solid var(--border) !important; padding-top: 14px !important; padding-bottom: 14px !important; }}
.pd-arena-name {{ font-size: 14px; }}
.pd-prop-row td {{ padding-left: 20px !important; }}
.pd-indent {{ color: var(--text-muted); font-size: 11px; margin-right: 4px; }}
.pd-emerging {{ text-align: center; width: 80px; font-size: 13px; color: var(--green); }}
.pd-footnote {{ font-size: 11px; color: var(--text-muted); text-align: center; margin-top: 12px; font-style: italic; line-height: 1.5; }}

/* Standing Context — unified arena cards */
.standing-arena-grid {{ display: flex; flex-direction: column; gap: 16px; }}
.standing-arena-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--card-radius); box-shadow: var(--card-shadow); overflow: hidden; }}
.arena-narrative {{ font-family: 'Lora', Georgia, serif; font-size: 13px; color: var(--text-mid); line-height: 1.7; padding: 0 18px 12px; }}

/* Inline strength/vulnerability signals within standing context */
.standing-signals {{ padding: 12px 18px 14px; margin: 10px 0 6px; border-radius: 6px; border-top: none; }}
.standing-signals-strength {{ background: rgba(46,155,110,0.06); border-left: 3px solid var(--green); }}
.standing-signals-vuln {{ background: rgba(217,64,72,0.06); border-left: 3px solid var(--red); }}
.standing-signal-head {{ font-size: 12px; font-weight: 700; color: var(--text); margin-bottom: 8px; display: flex; align-items: center; gap: 6px; text-transform: uppercase; letter-spacing: 0.5px; }}
.ss-icon {{ font-size: 10px; }}
.ss-icon-strength {{ color: var(--green); }}
.ss-icon-vuln {{ color: var(--red); }}
.standing-signals ul {{ list-style: none; padding: 0; }}
.standing-signals li {{ font-size: 12px; color: var(--text-mid); line-height: 1.65; margin-bottom: 6px; padding-left: 16px; position: relative; }}
.standing-signals-strength li::before {{ content: '+'; position: absolute; left: 0; color: var(--green); font-weight: 700; }}
.standing-signals-vuln li::before {{ content: '−'; position: absolute; left: 0; color: var(--red); font-weight: 700; font-size: 14px; }}
.standing-signals li strong {{ color: var(--text); font-weight: 600; }}
.signal-horizon-tag {{ font-size: 9px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; padding: 2px 8px; border-radius: 3px; background: var(--bg); border: 1px solid var(--border); color: var(--text-muted); margin-left: 4px; white-space: nowrap; }}
.sev-tag {{ font-size: 9px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; padding: 2px 8px; border-radius: 3px; }}
.sev-tag-high {{ background: rgba(217,64,72,0.12); color: #991b1b; }}
.sev-tag-medium {{ background: rgba(196,146,10,0.1); color: #92400e; }}
.sev-tag-low {{ background: var(--bg); color: var(--text-muted); border: 1px solid var(--border); }}

/* Redirect sections (Sections 7, 8) — styled as subtle cross-references */
.sec-redirect {{ opacity: 1; }}
.sec-redirect .sec-head {{ border-bottom: none; padding-bottom: 0; margin-bottom: 4px; }}
.sec-redirect .sec-title {{ font-size: 13px; color: var(--text-muted); font-weight: 600; }}
.sec-redirect .sec-num {{ font-size: 9px; }}
.redirect-text {{ font-size: 12px; color: var(--text-muted); font-style: italic; line-height: 1.5; padding: 8px 14px; background: var(--bg); border-left: 3px solid var(--border); border-radius: 0 4px 4px 0; margin: 0; }}
.redirect-text em {{ color: var(--pillar); font-style: normal; font-weight: 600; }}

/* Strategic Priorities — risk/opportunity framing */
.priority-type-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
.priority-type {{ font-size: 9px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; padding: 4px 12px; border-radius: 3px; }}
.pri-risk {{ background: rgba(217,64,72,0.12); color: #991b1b; }}
.pri-opportunity {{ background: rgba(46,155,110,0.12); color: #166534; }}
.pri-watch {{ background: rgba(196,146,10,0.1); color: #92400e; }}
.priority-arena-tag {{ font-size: 10px; font-weight: 600; color: var(--pillar); background: var(--pillar-light); padding: 3px 10px; border-radius: 3px; }}
.priority-response {{ font-size: 12px; color: var(--text-mid); line-height: 1.6; margin-top: 6px; padding-top: 6px; border-top: 1px dashed var(--border-light); }}
.priority-response strong {{ color: var(--text); }}

/* Forward Outlook / Predictions */
.pred-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
.pred-tile {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--card-radius); padding: 22px 24px; box-shadow: var(--card-shadow); transition: transform 0.15s, box-shadow 0.15s; }}
.pred-tile:hover {{ transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,0,0,0.08); }}
.pred-prob {{ font-family: 'Lora', Georgia, serif; font-size: 26px; font-weight: 700; color: #0d7680; line-height: 1; margin-bottom: 8px; }}
.pred-title {{ font-family: 'Inter', sans-serif; font-size: 14px; font-weight: 600; color: var(--text); line-height: 1.4; margin-bottom: 12px; }}
.pred-badges {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }}
.pred-badge {{ font-size: 9px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; padding: 4px 10px; border-radius: 3px; }}
.pred-type-strength {{ background: #0d7680; color: white; }}
.pred-type-vuln {{ background: var(--red); color: white; }}
.pred-dir-intensifying {{ background: #7C3AED; color: white; }}
.pred-dir-stable {{ background: #374151; color: white; }}
.pred-dir-fading {{ background: rgba(46,155,110,0.85); color: white; }}
.pred-dir-reversing {{ background: rgba(74,111,165,0.85); color: white; }}
.pred-signal-strong {{ background: #166534; color: white; }}
.pred-horizon {{ background: #f3f4f6; color: #374151; border: 1px solid #d1d5db; }}
.pred-trigger {{ font-size: 12px; color: var(--text-muted); line-height: 1.5; margin-top: 4px; }}
.pred-trigger strong {{ color: var(--text-mid); font-weight: 600; }}
.pred-summary {{ font-size: 12px; color: var(--text-muted); text-align: center; margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border-light); font-style: italic; }}
.arena-outlook {{ font-family: 'Lora', Georgia, serif; font-size: 12px; font-style: italic; color: var(--accent); padding: 8px 18px 12px; border-top: 1px solid var(--border-light); line-height: 1.6; }}

/* Methodology box */
.methodology-box {{ max-width: 1100px; margin: 48px auto 0; padding: 0 32px; }}
.methodology-box-inner {{ background: var(--bg-card); border: 1px solid var(--border); border-top: 3px solid var(--accent); border-radius: var(--card-radius); padding: 28px 32px; box-shadow: var(--card-shadow); }}
.methodology-box-text {{ font-family: 'Lora', Georgia, serif; font-size: 13px; color: var(--text-mid); line-height: 1.7; margin-bottom: 16px; }}
.methodology-box-cta {{ display: inline-flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 600; color: var(--accent); text-decoration: none; padding: 10px 20px; border: 1px solid var(--accent); border-radius: 6px; white-space: nowrap; transition: all 0.15s; }}
.methodology-box-cta:hover {{ background: var(--accent); color: white; }}

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
.footer-logo {{ font-family: 'Montserrat', sans-serif; font-weight: 700; font-size: 13px; letter-spacing: 0.06em; color: rgba(255,255,255,0.9); text-transform: uppercase; }}
.footer-label {{ font-size: 10px; font-weight: 400; color: rgba(255,255,255,0.45); }}
.footer-text {{ font-size: 10px; color: rgba(255,255,255,0.45); }}
.footer-credit {{ font-size: 9px; color: rgba(255,255,255,0.3); text-align: center; max-width: 1100px; margin: 12px auto 0; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.06); }}

/* Responsive */
@media (max-width: 900px) {{
  .hero-inner {{ flex-direction: column; padding: 32px 16px 0; min-height: auto; }}
  .hero-left {{ max-width: 100%; }}
  .hero-title {{ font-size: 32px; }}
  .score-block {{ width: 100%; margin-top: 24px; }}
  .score-block-inner {{ display: flex; align-items: center; gap: 16px; padding: 16px 20px; text-align: left; }}
  .score-block-label {{ display: none; }}
  .score-block-num {{ font-size: 48px; }}
  .score-block-max {{ display: none; }}
  .topbar {{ padding: 0 16px; height: 48px; }}
  .main {{ padding: 0 16px; }}
  .key-stats {{ grid-template-columns: repeat(3, 1fr); }}
  .key-stat-num {{ font-size: 24px; }}
  .arena-grid {{ grid-template-columns: 1fr; }}
  .pred-grid {{ grid-template-columns: 1fr; }}
  .arena-strip {{ flex-wrap: wrap; }}
  .arena-gauge {{ min-width: 33%; }}
  .pd-table {{ font-size: 12px; }}
  .pd-prop {{ max-width: 250px; }}
  .signal-card {{ padding: 16px; }}
  .signal-card-header {{ gap: 6px; }}
  .exec-card {{ padding: 20px; }}
  .conclusion-card {{ padding: 20px; }}
  .source-section {{ padding: 20px 16px; }}
  .footer {{ padding: 20px 16px; }}
  .footer-inner {{ flex-direction: column; gap: 8px; text-align: center; }}
  .pillar-nav a {{ font-size: 8px; padding: 3px 6px; }}
}}
@media (max-width: 600px) {{
  .topbar-brand {{ display: none; }}
  .topbar-divider {{ display: none; }}
  .topbar-logo {{ font-size: 17px; }}
  .hero-inner {{ padding: 24px 16px 0; }}
  .hero-title {{ font-size: 24px; }}
  .hero-desc {{ display: none; }}
  .key-stats {{ grid-template-columns: repeat(2, 1fr); }}
  .key-stat-num {{ font-size: 22px; }}
  .key-stat {{ padding: 14px 8px; }}
  .signal-table {{ font-size: 12px; }}
  .signal-table thead th {{ padding: 8px 12px; }}
  .signal-table tbody td {{ padding: 8px 12px; }}
  .pred-grid {{ grid-template-columns: 1fr; }}
  .pred-prob {{ font-size: 22px; }}
  .pillar-nav {{ display: none; }}
  .back-link {{ display: none; }}
}}
</style>
</head>
<body>
<div class="topbar">
  <div class="topbar-left">
    <a href="index.html" class="topbar-logo" style="text-decoration:none;color:rgba(255,255,255,0.9)">DipTel</a>
    <div class="topbar-divider"></div>
    <div class="pillar-nav">{pillar_nav_items}</div>
  </div>
  <div class="topbar-right">
    <span class="topbar-date">{display_date}</span>
  </div>
</div>

<div class="hero">
  <div class="hero-bg"></div>
  <div class="hero-inner">
    <div class="hero-left">
      <span class="hero-tag">{pillar['short']}</span>
      <h1 class="hero-title">{title_html}</h1>
      <div class="hero-meta">United Kingdom &mdash; {display_date} &middot; Ref: {ref_code}</div>
      <p class="hero-desc">{html.escape(_fix_emdashes(exec_summary[:200]))}</p>
    </div>
    <div class="score-block">
      <div class="score-block-inner">
        <div class="score-block-label">Pillar Score</div>
        <div class="score-block-num" style="color:{hero_score_color}">{score}{hero_score_arrow}</div>
        <div class="score-block-max">of 100</div>
        <div class="posture posture-{posture_cls}">{posture}</div>
      </div>
    </div>
  </div>
</div>

{('<div class="arena-strip">' + arena_strip_html + '</div>') if arena_strip_html else ''}

<div class="main">

  <!-- Section 02: Executive Intelligence Summary -->
  <div class="sec">
    <div class="sec-head">
      <h2 class="sec-title">Executive Intelligence Summary</h2>
      <span class="sec-num">Section 02</span>
    </div>
    <div class="exec-card">
{exec_html}    </div>
  </div>

  <!-- Signal Summary -->
  {stats_html}

  <!-- Section 03: Forward Outlook -->
  <div class="sec">
    <div class="sec-head">
      <h2 class="sec-title">Forward Outlook</h2>
      <span class="sec-num">Section 03</span>
    </div>
    {outlook_html}
  </div>

  <!-- Section 04: Sovereign Perception Dashboard -->
  <div class="sec">
    <div class="sec-head">
      <h2 class="sec-title">Sovereign Perception Dashboard</h2>
      <span class="sec-num">Section 04</span>
    </div>
    {perception_html if perception_html else '<div class="exec-card"><p>External perception data not available this cycle. Scores will populate when source coverage meets the assessment threshold.</p></div>'}
  </div>

  {profile_section_html}

  <!-- Section 06: Sovereign Standing Context -->
  <div class="sec">
    <div class="sec-head">
      <h2 class="sec-title">Sovereign Standing Context</h2>
      <span class="sec-num">Section 06 &middot; {len(arena_ctx)} arena{"s" if len(arena_ctx) != 1 else ""} assessed</span>
    </div>
    {('<div class="standing-arena-grid">' + standing_context_html + '</div>') if standing_context_html else '<div class="exec-card"><p>No arenas met the assessment threshold this cycle. Standing context will populate when sufficient source coverage is detected.</p></div>'}
  </div>

  <!-- Section 07: Vulnerability Signals (redirect) -->
  <div class="sec sec-redirect">
    <div class="sec-head">
      <h2 class="sec-title">Vulnerability Signals</h2>
      <span class="sec-num">Section 07</span>
    </div>
    <p class="redirect-text">Vulnerability signals are presented inline within each arena in Section 06 above. See <em>&ldquo;Pressure on this standing&rdquo;</em> blocks for detail.</p>
  </div>

  <!-- Section 08: Strength Signals (redirect) -->
  <div class="sec sec-redirect">
    <div class="sec-head">
      <h2 class="sec-title">Strength Signals</h2>
      <span class="sec-num">Section 08</span>
    </div>
    <p class="redirect-text">Strength signals are presented inline within each arena in Section 06 above. See <em>&ldquo;Reinforcing this standing&rdquo;</em> blocks for detail.</p>
  </div>

  {contradictions_section_html}

  {diagnostic_section_html}

  <!-- Section 11: Strategic Priorities -->
  <div class="sec">
    <div class="sec-head">
      <h2 class="sec-title">Strategic Attention Priorities</h2>
      <span class="sec-num">Section 11</span>
    </div>
    {priorities_html if priorities_html else '<div class="exec-card"><p>No strategic priorities flagged this cycle.</p></div>'}
  </div>

  <!-- Section 12: Position Summary -->
  <div class="sec">
    <div class="sec-head">
      <h2 class="sec-title">Position Summary</h2>
      <span class="sec-num">Section 12</span>
    </div>
    {overview_html if overview_html else '<div class="exec-card"><p>Position summary not assessed this cycle.</p></div>'}
  </div>

  <!-- Section 13: Conclusion -->
  <div class="sec">
    <div class="sec-head">
      <h2 class="sec-title">Conclusion</h2>
      <span class="sec-num">Section 13</span>
    </div>
    <div class="conclusion-card">
{conclusion_html}      <div class="conclusion-posture">
        Standing posture this cycle: <span class="conclusion-posture-badge posture-{posture_cls}">{posture}</span>
      </div>
    </div>
  </div>

</div>

{source_section}

<div class="methodology-box">
  <div class="methodology-box-inner">
    <div class="methodology-box-text">Sovereign Signal applies narrative signal processing to over 1.6 million sources daily &mdash; reducing billions of data points into actionable intelligence on sentiment, trends, and predictions.</div>
    <a class="methodology-box-cta" href="methodology.html">See Full Methodology &rarr;</a>
  </div>
</div>

<div class="footer">
  <div class="footer-inner">
    <div class="footer-left">
      <span class="footer-logo">Powered by NOAH</span>
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
    # Prefer the FIRST (newest) match per pillar from the RSS feed,
    # but also track all GUIDs per pillar for prediction scraping.
    pillar_items = {}
    pillar_guids = {}  # key -> list of all GUIDs for this pillar
    for item in day_items:
        pkey = classify_pillar(item["title"], item.get("description", ""))
        if pkey:
            guid = item.get("guid", "")
            pillar_guids.setdefault(pkey, [])
            if guid:
                pillar_guids[pkey].append(guid)
            # Keep the FIRST (newest) item per pillar — RSS feeds are newest-first
            if pkey not in pillar_items:
                pillar_items[pkey] = item
                print(f"    {PILLARS[pkey]['short']:20s} -> {item['title'][:60]}...")
            else:
                print(f"    {PILLARS[pkey]['short']:20s}    (also: {item['title'][:50]}...)")
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

        # Fetch predictions and richer perception data from rendered report pages
        # GUIDs are ordered newest-first; first data wins (most recent report)
        got_sv = False
        got_arena_preds = False
        for guid in pillar_guids.get(key, []):
            print(f"      Fetching predictions from rendered report ({guid[:12]})...")
            preds, arena_preds_scraped, rendered_perc = fetch_predictions_from_rendered(guid)
            if preds and not pdata["predictions"]:
                pdata["predictions"] = preds
                print(f"      Found {len(preds)} predictions")
            # Only use arena predictions from the FIRST (newest) report that has them
            # RSS-parsed arena_predictions are authoritative; scraped ones fill gaps only
            if arena_preds_scraped and not got_arena_preds:
                for arena_key, arena_val in arena_preds_scraped.items():
                    if arena_key not in pdata["arena_predictions"]:
                        pdata["arena_predictions"][arena_key] = arena_val
                got_arena_preds = True
                print(f"      Found {len(arena_preds_scraped)} arena outlooks (filling gaps)")
            # Use rendered perception data if it has sovereign_view (more accurate)
            # Only use the FIRST (newest) rendered page's SV data
            if rendered_perc and not got_sv:
                has_sv = any(p.get("sovereign_view") is not None for p in rendered_perc)
                if has_sv:
                    pdata["perception_dashboard"] = rendered_perc
                    # Recompute score from sovereign_view
                    # If arena-grouped, use only arena summary rows to avoid double-counting
                    has_arena_groups = any(p.get("is_arena_summary") for p in rendered_perc)
                    if has_arena_groups:
                        sv_scores = [p["sovereign_view"] for p in rendered_perc
                                     if p.get("is_arena_summary") and p.get("sovereign_view") is not None]
                    else:
                        sv_scores = [p["sovereign_view"] for p in rendered_perc if p.get("sovereign_view") is not None]
                    if sv_scores:
                        pdata["score"] = round(sum(sv_scores) / len(sv_scores))
                        print(f"      Updated score from rendered sovereign view: {pdata['score']}")
                    got_sv = True
            if preds and got_sv and got_arena_preds:
                break  # Got predictions, SV data, and arena outlooks from newest report

        pillar_data[key] = pdata
        print(f"      Score: {pdata.get('score', '?')}, Posture: {pdata.get('posture', '?')}, "
              f"Trends: {pdata['trend_count']}, Strengths: {pdata['strength_count']}, Vulns: {pdata['vuln_count']}")

    # Save data
    print("\n  Saving data...")
    history = save_day_data(target_date, pillar_data)

    # Compute per-pillar deltas for pillar reports
    prev_date = None
    for d in sorted(history.keys()):
        if d < target_date:
            prev_date = d
    if prev_date and prev_date in history:
        prev_scores = history[prev_date]
        for key in pillar_data:
            prev_s = prev_scores.get(key, {}).get("score")
            curr_s = pillar_data[key].get("score")
            if prev_s is not None and curr_s is not None:
                pillar_data[key]["_delta"] = curr_s - prev_s

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
