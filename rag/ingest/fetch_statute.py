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

import httpx
from bs4 import BeautifulSoup

from models import LegalSection

CHAPTER_URL = (
    "https://uscode.house.gov/view.xhtml"
    "?edition=prelim&path=%2Fprelim%40title20%2Fchapter33"
)


def fetch_chapter_html() -> str:
    """Fetch the raw HTML for 20 U.S.C. Chapter 33.

    TODO(you):
      1. GET CHAPTER_URL with httpx. Some government sites reject requests
         with no User-Agent header - if you get blocked, try passing
         headers={"User-Agent": "Mozilla/5.0"}.
      2. Raise on non-200 (response.raise_for_status()).
      3. Return response.text.
    """
    raise NotImplementedError


def parse_sections(html_text: str) -> list[LegalSection]:
    """Parse the chapter page into one LegalSection per section.

    TODO(you):
      1. Parse `html_text` with BeautifulSoup(html_text, "lxml").
      2. Find every <h3 class="section-head"> tag - each one marks the
         start of a new section (soup.find_all("h3", class_="section-head")).
      3. For each heading tag:
           - Its text (tag.get_text()) contains the section number and
             title, e.g. "\xa71400. Short title; findings; purposes" -
             you'll need to strip the leading "\xa7" (that's the § symbol)
             and split off the number from the rest.
           - The section's body is everything between this heading and the
             *next* <h3 class="section-head"> tag - look at
             tag.find_next_siblings() and stop collecting once you hit
             another section-head, or use tag.find_next("h3", ...) to find
             the boundary.
      4. Build a LegalSection per section:
           source_type="statute"
           citation=f"20 U.S.C. § {section_number}"
           heading=<the title text after the number>
           text=<the concatenated body text>
           source_url=CHAPTER_URL
      5. Return the list.

    Print soup.prettify()[:3000] or look at a saved copy of the HTML in
    your browser if you get stuck on the actual tag layout - don't guess
    blind.
    """
    raise NotImplementedError


def main() -> list[LegalSection]:
    html_text = fetch_chapter_html()
    # TODO(optional): cache html_text to ../data/raw/20-usc-ch33.html so
    # re-running this script during development doesn't re-hit the site
    # every time.
    return parse_sections(html_text)


if __name__ == "__main__":
    sections = main()
    print(f"Parsed {len(sections)} sections from 20 U.S.C. Chapter 33")
    for s in sections[:3]:
        print(f"  {s.citation}: {s.heading}")
