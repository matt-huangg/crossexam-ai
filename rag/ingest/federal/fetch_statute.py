"""Fetch IDEA statute text (20 U.S.C. Chapter 33) from uscode.house.gov.

Unlike 34 CFR (fetch_cfr.py), there is no clean REST API for the US Code -
the Office of Law Revision Counsel only ships bulk XML downloads of entire
titles. uscode.house.gov does render a whole chapter as one browsable HTML
page though, which is simpler for us since we only need one chapter, not
all of Title 20.

Confirmed page structure (fetched and inspected manually before writing
this) - each section looks like:

    <!-- documentid:20_1400  usckey:... -->
    <h3 class="section-head">&sect;1400. Short title; findings; purposes</h3>
    <h4 class="subsection-head">(a) Short title</h4>
    <p class="statutory-body">This chapter may be cited as ...</p>
    ...
    (next section's <!-- documentid:... --> comment starts here)

Notice the HTML comment right before each heading, e.g.
"documentid:20_1400" - that's a more reliable way to find where a section
starts than parsing the visible "&sect;1400." text, which is a general
scraping lesson worth remembering: look for stable machine-oriented
markers in the raw source, not just what's visually rendered.
"""

import re

import httpx
from bs4 import BeautifulSoup

from ingest.cache import (
    PROCESSED_DIR,
    RAW_DIR,
    load_processed,
    load_raw_text,
    save_processed,
    save_raw_text,
)
from ingest.models import LegalSection

CHAPTER_URL = (
    "https://uscode.house.gov/view.xhtml"
    "?edition=prelim&path=%2Fprelim%40title20%2Fchapter33"
)
STATUTE_RAW_PATH = RAW_DIR / "20-usc-ch33.html"
STATUTE_PROCESSED_PATH = PROCESSED_DIR / "20-usc-ch33.json"

# Headings look like "1400. Short title; findings; purposes" (sometimes
# with a leading section symbol).
HEADING_RE = re.compile(r"^§?\s*(\d+[A-Za-z]?)\.\s*(.+)$")


def fetch_chapter_html() -> str:
    """Fetch the raw HTML for 20 U.S.C. Chapter 33."""
    response = httpx.get(
        CHAPTER_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=60.0,
    )
    response.raise_for_status()
    return response.text


def _section_body_text(heading_tag) -> str:
    """Collect subsection headings and statutory paragraphs until the next section."""
    parts = []
    for sibling in heading_tag.find_next_siblings():
        if sibling.name == "h3" and "section-head" in (sibling.get("class") or []):
            break
        if sibling.name in ("h4", "p"):
            text = sibling.get_text().strip()
            if text:
                parts.append(text)
    return "\n".join(parts)


def parse_sections(html_text: str, source_url: str = CHAPTER_URL) -> list[LegalSection]:
    """Parse the chapter page into one LegalSection per section."""
    soup = BeautifulSoup(html_text, "xml")
    sections = []
    for head in soup.find_all("h3", class_="section-head"):
        raw_heading = head.get_text().strip()
        match = HEADING_RE.match(raw_heading)
        if not match:
            continue

        section_number, heading = match.groups()
        text = _section_body_text(head)
        if not text:
            continue

        sections.append(
            LegalSection(
                source_type="statute",
                citation=f"20 U.S.C. § {section_number}",
                heading=heading.strip(),
                text=text,
                source_url=source_url,
            )
        )
    return sections


def main(*, use_cache: bool = True) -> list[LegalSection]:
    if use_cache:
        cached = load_processed(STATUTE_PROCESSED_PATH)
        if cached is not None:
            return cached

    html_text = load_raw_text(STATUTE_RAW_PATH) if use_cache else None
    if html_text is None:
        html_text = fetch_chapter_html()
        if use_cache:
            save_raw_text(STATUTE_RAW_PATH, html_text)

    sections = parse_sections(html_text, source_url=CHAPTER_URL)
    if use_cache:
        save_processed(STATUTE_PROCESSED_PATH, sections)
    return sections


if __name__ == "__main__":
    statute_sections = main()
    print(f"Parsed {len(statute_sections)} sections from 20 U.S.C. Chapter 33")
    for s in statute_sections[:3]:
        print(f"  {s.citation}: {s.heading}")
