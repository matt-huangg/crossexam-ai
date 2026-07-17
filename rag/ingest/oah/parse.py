"""Parse extracted OAH decision text into HearingDecision records.

Also provides LEA (school district) matching helpers used to keep the MVP
slice (e.g. San Diego Unified) after statewide discovery/download.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from ingest.models import HearingDecision

DEFAULT_LEA_FILTERS = (
    "San Diego Unified",
    # "Grossmont", "Poway", "Sweetwater",  # widen if the MVP set is too thin
)

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


def _clean_caption_line(line: str) -> str:
    cleaned = line.strip().rstrip(",.").strip()
    cleaned = re.sub(r",?\s*Respondent\.?\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r",?\s*Petitioner[s]?\.?\s*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip().rstrip(".")


def _score_lea_line(line: str) -> int:
    """Higher score = more likely the respondent district caption line."""
    stripped = line.strip()
    if not stripped or len(stripped) > 200:
        return -1

    upper = stripped.upper()
    if not any(cue in upper for cue in ("SCHOOL DISTRICT", "UNIFIED", "UNION HIGH")):
        return -1

    score = 0
    if "SCHOOL DISTRICT" in upper:
        score += 5
    if "UNIFIED" in upper:
        score += 3
    if "UNION HIGH" in upper:
        score += 3
    if "RESPONDENT" in upper:
        score += 2
    if re.search(
        r"\b(?:OFFICE OF ADMINISTRATIVE HEARINGS|STATE OF CALIFORNIA|"
        r"DECISION AFTER|FINDINGS OF FACT)\b",
        upper,
    ):
        score -= 4
    return score


def _extract_lea(head: str, filters: tuple[str, ...]) -> str:
    best_line = ""
    best_score = 0
    for raw_line in head.splitlines():
        line = _clean_caption_line(raw_line)
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
    lea_filters: tuple[str, ...] = DEFAULT_LEA_FILTERS,
) -> HearingDecision:
    """Build a HearingDecision from extracted text + filename metadata."""
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
