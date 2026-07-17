"""Parse extracted OAH decision text into HearingDecision records.

Also provides optional LEA (school district) matching helpers for callers
that want a district slice. Statewide ingest keeps every parsed decision
and stores ``lea`` as metadata.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from ingest.models import HearingDecision

CASE_ID_RE = re.compile(r"(\d{7,10})")
CASE_NO_IN_TEXT_RE = re.compile(
    r"(?:Case\s+(?:No\.?|Number:?)\s*)[:\s]*(\d{7,10})",
    re.IGNORECASE,
)
HEADING_SKIP_RE = re.compile(
    r"^(?:office of administrative hearings|state of california|"
    r"special education|decision|order|before the|case no\.?|\d{1,3})$",
    re.IGNORECASE,
)
HEAD_SCAN_CHARS = 4000

_DATE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "%Y-%m-%d"),
    (
        re.compile(
            r"\b(?:January|February|March|April|May|June|July|August|"
            r"September|October|November|December)\s+\d{1,2},\s+\d{4}\b",
            re.IGNORECASE,
        ),
        "%B %d, %Y",
    ),
    (
        re.compile(
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?"
            r"\s+\d{1,2},\s+\d{4}\b",
            re.IGNORECASE,
        ),
        "%b %d, %Y",
    ),
    (re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"), "%m/%d/%Y"),
)


def lea_matches(lea: str, filters: tuple[str, ...]) -> bool:
    """True if any filter is a case-insensitive substring of ``lea``."""
    if not filters:
        return True
    lea_fold = lea.casefold()
    return any(f.casefold() in lea_fold for f in filters if f)


def matches_lea_filters(text: str, lea: str, filters: tuple[str, ...]) -> bool:
    """True if filters match parsed LEA or appear in the decision head."""
    if lea_matches(lea, filters):
        return True
    if not filters:
        return True
    head = text[:HEAD_SCAN_CHARS].casefold()
    return any(f.casefold() in head for f in filters if f)


# Caption party fragments that are the student/parent side, not the LEA.
_STUDENT_PARTY_RE = re.compile(
    r"^(?:parents?|parent|guardians?|student)\b|"
    r"\bon behalf of student\b|"
    r"^the consolidated matters",
    re.IGNORECASE,
)

# Prose / cite lines that sometimes contain "School District" but are not the caption.
_PROSE_LEA_RE = re.compile(
    r"\b(?:naming|named|sch\.\s*dist|due process|administrative law|"
    r"9th cir|u\.s\.c|ed\.\s*code)\b",
    re.IGNORECASE,
)

# Non-district LEAs are common in OAH (charters, city schools, COEs).
_LEA_CUES: tuple[tuple[str, int], ...] = (
    ("SCHOOL DISTRICT", 5),
    ("CITY SCHOOLS", 5),
    ("COUNTY OFFICE OF EDUCATION", 5),
    ("OFFICE OF EDUCATION", 4),
    ("CHARTER SCHOOL", 5),
    ("CHARTER", 4),  # e.g. "SEBASTOPOL INDEPENDENT CHARTER"
    ("FAMILY OF SCHOOLS", 5),
    ("UNIFIED", 3),
    ("UNION HIGH", 3),
    ("UNION ", 2),  # "CUPERTINO UNION SCHOOL DISTRICT" after soft-wrap fix
    ("ACADEMY", 4),
    ("SELPA", 2),
)

# Parties live between the court header and the DECISION title — whether
# CASE NO. appears above or below the party names.
_CAPTION_REGION_RE = re.compile(
    r"STATE\s+OF\s+CALIFORNIA\s*(.*?)\b(?:EXPEDITED\s+)?DECISION\b",
    re.IGNORECASE | re.DOTALL,
)


def _clean_caption_line(line: str) -> str:
    cleaned = line.strip().rstrip(",.").strip()
    # Consolidated captions prefix the LEA after a colon.
    cleaned = re.sub(
        r"^THE CONSOLIDATED MATTERS INVOLVING:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r",?\s*Respondent\.?\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r",?\s*Petitioner[s]?\.?\s*$", "", cleaned, flags=re.IGNORECASE)
    # Soft-wrap artifact: "CUPERTINO UNION S CHOOL" → "CUPERTINO UNION SCHOOL"
    cleaned = re.sub(r"\b([A-Z]) ([A-Z]{2,})\b", r"\1\2", cleaned)
    # Trailing versus marker left after a bad join: "PETALUMA CITY SCHOOLS, V"
    cleaned = re.sub(r",?\s*[Vv]\.?\s*$", "", cleaned).strip().rstrip(",.")
    # Remand/order titles sometimes glue onto the party line after the
    # first period — keep only the party name sentence.
    if ". " in cleaned:
        first, rest = cleaned.split(". ", 1)
        if any(cue in first.upper() for cue, _ in _LEA_CUES) and _PROSE_LEA_RE.search(
            rest
        ):
            cleaned = first
    return cleaned.strip()


def _caption_party_candidates(head: str) -> list[str]:
    """Party-name candidates from the caption block (not body prose).

    CASE NO. can appear above *or* below the parties, so we take the region
    from ``STATE OF CALIFORNIA`` through ``DECISION``, drop case-number
    lines, then split on ``v.`` / ``AND`` into party fragments.
    """
    match = _CAPTION_REGION_RE.search(head)
    region = match.group(1) if match else head[:1500]

    # Drop "CASE NO. 2022080550" lines; they aren't parties.
    region = re.sub(
        r"CASE\s+NO\.?\s*:?\s*\d{7,10}", " ", region, flags=re.IGNORECASE
    )
    # Newlines → spaces so soft-wrapped LEA names become one fragment.
    flat = re.sub(r"\s+", " ", region).strip()
    if not flat:
        return []

    # Split adversarial captions ("Student v. District") and consolidated
    # captions ("District, AND Parents..."). Use `, AND` (comma required)
    # so names like "ACADEMY OF SCIENCE AND CULTURAL ARTS" stay intact.
    # Avoid `\b` after `v.` — the period is non-word so `\b` never fires
    # before the following space.
    parts = re.split(
        r"\s+v\.?\s+|\s+vs\.?\s+|,\s+AND\s+",
        flat,
        flags=re.IGNORECASE,
    )
    return [p.strip(" ,.") for p in parts if p.strip(" ,.")]


def _score_lea_line(line: str) -> int:
    """Higher score = more likely the LEA / public-agency caption party."""
    stripped = line.strip()
    if not stripped or len(stripped) > 220:
        return -1

    upper = stripped.upper()
    if _STUDENT_PARTY_RE.search(stripped):
        return -1
    if _PROSE_LEA_RE.search(stripped):
        return -1
    if re.search(
        r"\b(?:OFFICE OF ADMINISTRATIVE HEARINGS|STATE OF CALIFORNIA|"
        r"DECISION AFTER|FINDINGS OF FACT|ACCESSIBILITY MODIFIED)\b",
        upper,
    ):
        return -1

    score = 0
    for cue, points in _LEA_CUES:
        if cue in upper:
            score += points
    if score == 0:
        return -1

    if "RESPONDENT" in upper:
        score += 2
    # Short caption parties beat long body sentences that slipped through.
    if len(stripped) < 100:
        score += 1
    if stripped.isupper() and len(stripped) < 100:
        score += 1
    return score


def _extract_lea(head: str, filters: tuple[str, ...]) -> str:
    """Pick the best-scoring LEA party from the caption; else filter fallback."""
    best_line = ""
    best_score = 0
    for raw in _caption_party_candidates(head):
        line = _clean_caption_line(raw)
        score = _score_lea_line(line)
        if score > best_score:
            best_score = score
            best_line = line
    if best_line:
        return best_line

    head_fold = head.casefold()
    for filt in filters:
        if filt and filt.casefold() in head_fold:
            return (
                filt
                if "school district" in filt.casefold()
                else f"{filt} School District"
            )
    return "UNKNOWN LEA"


def _extract_case_id(pdf_path: Path, head: str) -> str:
    match = CASE_ID_RE.search(pdf_path.stem) or CASE_NO_IN_TEXT_RE.search(head)
    return match.group(1) if match else "UNKNOWN"


def _extract_decision_date(head: str) -> str:
    for pattern, fmt in _DATE_PATTERNS:
        match = pattern.search(head)
        if not match:
            continue
        try:
            return datetime.strptime(match.group(0), fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _extract_heading(text: str, case_id: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if len(line) < 15 or HEADING_SKIP_RE.match(line):
            continue
        return line[:120]
    return f"OAH {case_id}"


def parse_decision(
    pdf_path: Path,
    text: str,
    source_url: str,
    *,
    lea_filters: tuple[str, ...] = (),
) -> HearingDecision:
    """Build a HearingDecision from extracted text + filename metadata.

    ``lea_filters`` only helps ``_extract_lea`` fall back when caption
    scoring fails; it does not drop the record. Filtering belongs in the
    caller (see ``matches_lea_filters``).
    """
    body = text.strip()
    head = body[:HEAD_SCAN_CHARS]
    case_id = _extract_case_id(pdf_path, head)
    return HearingDecision(
        case_id=case_id,
        citation=f"OAH {case_id}",
        lea=_extract_lea(head, lea_filters),
        decision_date=_extract_decision_date(head),
        heading=_extract_heading(body, case_id),
        text=body,
        source_url=source_url,
    )
