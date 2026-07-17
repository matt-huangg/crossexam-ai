"""Discover OAH special-education decision PDF URLs via MediaSearch.

This is listing only — no downloads, no text extraction. The Decisions UI
calls the same Sitecore endpoint; we paginate its HTML fragments and return
url + display-filename pairs.
"""

from __future__ import annotations

import re
from datetime import date
from typing import NamedTuple

import httpx
from bs4 import BeautifulSoup

DGS_BASE_URL = "https://www.dgs.ca.gov"
MEDIA_SEARCH_API_URL = f"{DGS_BASE_URL}/api/Sitecore/MediaSearch/GetSearchResults"
MEDIA_SEARCH_FOLDER_PATH = (
    "/sitecore/media library/Divisions/OAH/Special Education/SE Decisions"
)
MEDIA_SEARCH_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    # Same ajax signal the Decisions page sends so we get the HTML fragment.
    "X-Requested-With": "XMLHttpRequest",
}

# Decision-after-hearing filenames (OAH naming is inconsistent with spaces).
DECISION_FILENAME_RE = re.compile(
    r"(?:Exp\s*Acc\s*Mod|ExpAccMod|AccMod|Acc)\.pdf$",
    re.IGNORECASE,
)
YEAR_FROM_FILENAME_RE = re.compile(r"^(\d{4})")


class PdfCandidate(NamedTuple):
    """One decision PDF from MediaSearch.

    Media hrefs are opaque UUID paths; keep the display ``filename`` so
    case_id can be recovered after download.
    """

    url: str
    filename: str


def default_years() -> list[int]:
    """Last five calendar years inclusive (current year-4 … current)."""
    year = date.today().year
    return list(range(year - 4, year + 1))


def _absolute_url(href: str) -> str:
    if href.startswith("http"):
        return href
    return f"{DGS_BASE_URL}{href if href.startswith('/') else '/' + href}"


def list_candidate_pdf_urls(*, years: list[int] | None = None) -> list[PdfCandidate]:
    """Paginate MediaSearch and return decision PDFs in the year window.

    Does not filter by LEA — district names are not in the listing. Filter
    after text extract in ``ingest.oah.fetch.main``.
    """
    if years is None:
        years = default_years()
    if not years:
        return []

    year_set = set(years)
    min_year = min(years)
    seen: set[str] = set()
    candidates: list[PdfCandidate] = []

    with httpx.Client(timeout=60.0) as client:
        page = 1
        while page <= 400:  # safety cap (~1931 docs / 10 per page)
            response = client.get(
                MEDIA_SEARCH_API_URL,
                params={
                    "page": page,
                    "folderPath": MEDIA_SEARCH_FOLDER_PATH,
                    "sortBy": "date_desc",
                },
                headers=MEDIA_SEARCH_HEADERS,
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")
            links = [
                (a["href"].strip(), a.get_text(strip=True))
                for a in soup.find_all("a", href=True)
                if ".pdf" in a["href"].lower()
            ]
            if not links:
                break

            page_years: list[int] = []
            for href, filename in links:
                year_match = YEAR_FROM_FILENAME_RE.match(filename)
                if year_match:
                    page_years.append(int(year_match.group(1)))

                if not DECISION_FILENAME_RE.search(filename):
                    continue
                if year_match is None or int(year_match.group(1)) not in year_set:
                    continue

                url = _absolute_url(href)
                if url in seen:
                    continue
                seen.add(url)
                candidates.append(PdfCandidate(url=url, filename=filename))

            # Newest-first: once a full page is older than the window, stop.
            if page_years and max(page_years) < min_year:
                break
            page += 1

    return candidates
