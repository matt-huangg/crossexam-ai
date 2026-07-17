"""Fetch 34 CFR Part 300 (federal special-education regulations) from the
eCFR.gov API.

Why Title 34, Part 300 specifically:

  - CrossExam AI rehearses cross-examination for IDEA due process hearings.
    The hearing officer and opposing counsel must ground rulings and
    objections in retrieved federal law — not freeform LLM reasoning.
  - Title 34 CFR is "Education," but most of it (higher ed, student aid,
    etc.) is irrelevant to special-ed disputes. Part 300 is the slice that
    matters: "Assistance to States for the Education of Children with
    Disabilities" — the Department of Education regulations that implement
    IDEA (20 U.S.C. Chapter 33, fetched separately in fetch_statute.py).
  - Together, the statute + Part 300 cover the procedural standards this
    product needs: prior notice, evaluation timelines, IEP content, due
    process complaint procedures, hearing rights, etc.
  - We fetch only Part 300 (not all of Title 34) to keep the corpus bounded
    and retrieval focused. The eCFR API supports a ``part`` query param for
    exactly this.

eCFR.gov is a genuine structured REST API (contrast with fetch_statute.py,
which has to scrape HTML) - no guessing at page structure needed, just read
the response format and parse it.

Confirmed response shape (fetched and inspected manually before writing
this): each section is a <DIV8 TYPE="SECTION"> element, e.g.:

    <DIV8 N="300.1" TYPE="SECTION" hierarchy_metadata="...">
    <HEAD>&#xA7; 300.1 Purposes.</HEAD>
    <P>The purposes of this part are&#x2014;</P>
    <P>(a) To ensure that all children with disabilities...</P>
    ...
    </DIV8>

- N="300.1" -> the section number
- <HEAD>    -> the section heading (first child)
- <P>...</P> (the rest) -> the section body, one paragraph per <P>
"""

import re
import xml.etree.ElementTree as ET

import httpx

from ingest.common.cache import (
    PROCESSED_DIR,
    RAW_DIR,
    load_meta,
    load_processed,
    load_raw_text,
    save_meta,
    save_processed,
    save_raw_text,
)
from ingest.common.models import LegalSection

TITLES_URL = "https://www.ecfr.gov/api/versioner/v1/titles.json"
FULL_TEXT_URL_TEMPLATE = "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-34.xml"
CFR_TITLE_NUMBER = 34
CFR_PART_NUMBER = 300
CFR_RAW_PATH = RAW_DIR / "34-cfr-300.xml"
CFR_META_PATH = RAW_DIR / "34-cfr-300.meta.json"
CFR_PROCESSED_PATH = PROCESSED_DIR / "34-cfr-300.json"


def get_latest_title_34_date() -> str:
    """Return the latest issue date (YYYY-MM-DD) available for Title 34."""
    response = httpx.get(TITLES_URL)
    response.raise_for_status()
    data = response.json()
    for title in data["titles"]:
        if title["number"] == CFR_TITLE_NUMBER:
            return title["latest_issue_date"]
    raise ValueError(f"Title {CFR_TITLE_NUMBER} not found in eCFR titles response")


def fetch_part_300_xml(issue_date: str) -> str:
    """Fetch the processed XML for 34 CFR Part 300 as of `issue_date`."""
    url = FULL_TEXT_URL_TEMPLATE.format(date=issue_date)
    response = httpx.get(url, params={"part": CFR_PART_NUMBER})
    response.raise_for_status()
    return response.text


def parse_sections(xml_text: str, source_url: str) -> list[LegalSection]:
    """Parse Part 300's XML into one LegalSection per section."""
    root = ET.fromstring(xml_text)
    sections = []
    for div8 in root.iter("DIV8"):
        if div8.get("TYPE") != "SECTION":
            continue

        head = div8.find("HEAD")
        raw_heading = "".join(head.itertext()).strip() if head is not None else ""
        heading = re.sub(r"^§\s*[\d.]+\s*", "", raw_heading).strip()

        paragraphs = ["".join(p.itertext()).strip() for p in div8.findall("P")]
        text = "\n".join(p for p in paragraphs if p)

        if not text:
            # "[Reserved]" sections (e.g. "§ 300.10 [Reserved]") have a
            # heading but no body - the agency left the number as a
            # placeholder rather than renumbering everything after it.
            # Nothing to retrieve here, so skip it rather than creating
            # an empty LegalSection.
            continue

        sections.append(
            LegalSection(
                source_type="cfr",
                citation=f"34 CFR § {div8.get('N')}",
                heading=heading,
                text=text,
                source_url=source_url,
            )
        )
    return sections


def main(*, use_cache: bool = True) -> list[LegalSection]:
    if use_cache:
        cached = load_processed(CFR_PROCESSED_PATH)
        if cached is not None:
            return cached

    if use_cache and (xml_text := load_raw_text(CFR_RAW_PATH)) is not None:
        meta = load_meta(CFR_META_PATH) or {}
        source_url = meta.get(
            "source_url",
            FULL_TEXT_URL_TEMPLATE.format(date=meta.get("issue_date", "unknown")),
        )
    else:
        date = get_latest_title_34_date()
        xml_text = fetch_part_300_xml(date)
        source_url = FULL_TEXT_URL_TEMPLATE.format(date=date)
        if use_cache:
            save_raw_text(CFR_RAW_PATH, xml_text)
            save_meta(
                CFR_META_PATH,
                {"issue_date": date, "source_url": source_url},
            )

    sections = parse_sections(xml_text, source_url=source_url)
    if use_cache:
        save_processed(CFR_PROCESSED_PATH, sections)
    return sections


if __name__ == "__main__":
    cfr_sections = main()
    print(f"Parsed {len(cfr_sections)} sections from 34 CFR Part 300")
    for s in cfr_sections[:100]:
        print(f"  {s.citation}: {s.heading}")
