"""Convert the supplied training plans into date-free, load-free app data.

Run this from the app folder after replacing either source document:
    <bundled-python> build_program_data.py
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pdfplumber
from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph


APP_DIR = Path(__file__).resolve().parent
SOURCE_DIR = APP_DIR.parent
OUTPUT_PATH = APP_DIR / "programs.js"

SOURCES = {
    "base": SOURCE_DIR / "Donald_Sibley_Workouts_Mar10_May28 (1).docx",
}

V2_SOURCE_DIR = Path(
    os.environ.get("BASE_BUILDER_V2_DIR", r"C:\Users\donsi\Downloads\BaseBuilderV2")
)
RACE_SOURCE_DIR = Path(
    os.environ.get("RACE_BUILDER_DIR", r"C:\Users\donsi\OneDrive\Desktop\Race buidler")
)

PROGRAM_META = {
    "base": {"title": "Base Builder", "weeks": 12},
    "base-v2": {"title": "Base Builder V2", "weeks": 12},
    "race": {"title": "Race Builder", "weeks": 14},
}

BULLET = "\u00b7"
EM_DASH = "\u2014"
EN_DASH = "\u2013"

DAY_HEADING = re.compile(r"^(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\b", re.I)
WEEK_HEADING = re.compile(r"^Week\s+(\d+)\b", re.I)
RPE_PATTERN = re.compile(r"(?:last\s+set\s+)?RPE\s*(\d+(?:\s*[\u2013\-/]\s*\d+)?)", re.I)
V2_DAY_HEADING = re.compile(
    r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*-",
    re.I,
)
RACE_SOURCE_DATE = re.compile(
    r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\.\s*(\d{1,2}),\s*(\d{4})",
    re.I,
)
RACE_MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


def clean_text(value: str) -> str:
    return " ".join(value.replace("\n", " ").replace(BULLET, f" {BULLET} ").split()).strip()


def section_title(value: str) -> str:
    """Make source headings readable without changing their workout meaning."""
    text = clean_text(value).replace(EM_DASH, EN_DASH)
    text = re.sub(r"\s+", " ", text)
    return text.title().replace("Runners Core", "Runner's Core").replace("Plyos", "Plyos")


def phase_label(heading: str) -> tuple[str, str]:
    """Return a short phase/focus label and the prescribed week RPE."""
    rpe_match = RPE_PATTERN.search(heading)
    week_rpe = f"RPE {rpe_match.group(1)}" if rpe_match else ""
    after_dash = re.split(r"\s+[\u2014-]\s+", heading, maxsplit=1)
    focus = after_dash[1] if len(after_dash) > 1 else ""
    focus = re.sub(r"\s*\(RPE[^)]*\)", "", focus, flags=re.I)
    focus = re.sub(rf"\s*{BULLET}\s*Final week.*$", "", focus, flags=re.I)
    return clean_text(focus), week_rpe


def prescription(values: list[str]) -> str:
    filled = [clean_text(value) for value in values if clean_text(value) not in {"", EM_DASH, "-"}]
    if not filled:
        return ""
    if all(value == filled[0] for value in filled):
        return f"{len(filled)} x {filled[0]}"
    return " / ".join(filled)


def clean_note(raw: str) -> tuple[str, str]:
    """Keep RPE and coaching notes while removing load and weight fragments."""
    value = clean_text(raw)
    if not value or value in {EM_DASH, "-"}:
        return "", ""

    rpe_match = RPE_PATTERN.search(value)
    rpe = f"RPE {rpe_match.group(1)}" if rpe_match else ""

    pieces = [clean_text(piece) for piece in re.split(rf"\s*{BULLET}\s*", value)]
    kept: list[str] = []
    for piece in pieces:
        if not piece:
            continue
        without_rpe = clean_text(RPE_PATTERN.sub("", piece))
        # Numeric maxes, kg amounts, and working percentages are load data.
        # Effort percentages are coaching notes, so they remain.
        is_numeric_max = bool(re.match(r"^max\s+\d", piece, flags=re.I))
        is_weight = bool(re.search(r"\bkg\b", piece, flags=re.I))
        is_working_percent = bool(
            re.search(r"\d+\s*%", piece)
            and "effort" not in piece.lower()
            and "rpe" not in piece.lower()
        )
        if is_numeric_max or is_weight or is_working_percent:
            continue
        # Do not duplicate RPE in the notes. Keep scopes such as "last set".
        if without_rpe:
            kept.append(without_rpe)

    return rpe, f" {BULLET} ".join(kept).strip(f" {BULLET}")


def table_rows(table: Table) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in table.rows[1:]:
        cells = [clean_text(cell.text) for cell in row.cells]
        if not any(cells):
            continue
        rpe, note = clean_note(cells[5] if len(cells) > 5 else "")
        item = {
            "name": cells[0],
            "prescription": prescription(cells[1:5]),
            "rpe": rpe,
            "note": note,
        }
        rows.append({key: value for key, value in item.items() if value})
    return rows


def iter_blocks(document: Document):
    """Yield paragraphs and tables in their original document order."""
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield "paragraph", Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield "table", Table(child, document)


def parse_program(program_id: str, source_path: Path) -> dict:
    document = Document(source_path)
    weeks: list[dict] = []
    current_week: dict | None = None
    current_session: dict | None = None
    current_section = ""

    for kind, block in iter_blocks(document):
        if kind == "paragraph":
            text = clean_text(block.text)
            if not text:
                continue

            week_match = WEEK_HEADING.match(text)
            if week_match and "RPE" in text and BULLET in text:
                focus, week_rpe = phase_label(text)
                current_week = {
                    "number": int(week_match.group(1)),
                    "focus": focus,
                    "rpe": week_rpe,
                    "sessions": [],
                }
                weeks.append(current_week)
                current_session = None
                current_section = ""
                continue

            if current_week and DAY_HEADING.match(text):
                current_session = {
                    "id": f"{program_id}-w{current_week['number']:02d}-s{len(current_week['sessions']) + 1}",
                    "label": f"Session {len(current_week['sessions']) + 1}",
                    "sections": [],
                }
                current_week["sessions"].append(current_session)
                current_section = ""
                continue

            if current_session and (text.isupper() or re.match(rf"^[A-D]\s*{BULLET}", text)):
                # All source section labels directly precede a table. Narrative
                # paragraphs are deliberately excluded from the compact app view.
                current_section = section_title(text)

        elif current_session and current_section:
            rows = table_rows(block)
            if rows:
                current_session["sections"].append(
                    {
                        "id": f"{current_session['id']}-section-{len(current_session['sections']) + 1}",
                        "title": current_section,
                        "exercises": rows,
                    }
                )
            current_section = ""

    expected_weeks = PROGRAM_META[program_id]["weeks"]
    if len(weeks) != expected_weeks:
        raise ValueError(f"{program_id}: expected {expected_weeks} weeks, found {len(weeks)}")
    for week in weeks:
        if len(week["sessions"]) != 3:
            raise ValueError(f"{program_id} week {week['number']}: expected 3 sessions, found {len(week['sessions'])}")
        for session in week["sessions"]:
            if not session["sections"]:
                raise ValueError(f"{session['id']}: no sections found")

    return {"id": program_id, "title": PROGRAM_META[program_id]["title"], "weeks": weeks}


def v2_section_title(value: str) -> str:
    """Map TeamBuildr's section labels into the app's readable section names."""
    text = clean_text(value)
    upper = text.upper()
    if "WARM UP/MOBILITY" in upper:
        return "Warm-Up / Mobility"
    if upper == "MOBILITY":
        return "Mobility"
    if "PLYOS" in upper:
        return "Plyos - Submaximal"
    if "MAIN STRENGTH" in upper:
        return "Main Strength"
    if "RUNNERS CORE" in upper:
        return "Runner's Core"
    if "RUNNERS HIPS" in upper:
        return "Runner's Hips"
    return ""


def v2_prescription_values(cells: list[str]) -> list[str]:
    """Read only the rep/time columns from a TeamBuildr exercise row."""
    max_index = next(
        (
            index
            for index, value in enumerate(cells)
            if value.upper() == "N/A" or re.fullmatch(r"\d+(?:\.\d+)?", value)
        ),
        -1,
    )
    if max_index < 0:
        return []

    values: list[str] = []
    for value in cells[max_index + 1 :]:
        lower = value.lower()
        if not value or "%" in value or "rpe" in lower:
            continue
        if lower in {"result", "reps"} or lower.startswith("set "):
            continue
        if re.search(r"\d", value):
            values.append(value)
    return values


def clean_v2_note(raw: str) -> tuple[str, str]:
    """Retain RPE, rest and technique while discarding all loading guidance."""
    value = clean_text(raw)
    if not value:
        return "", ""
    if "%" in value and "effort" not in value.lower():
        return "", ""

    rpe_match = RPE_PATTERN.search(value)
    rpe = f"RPE {rpe_match.group(1)}" if rpe_match else ""
    without_rpe = clean_text(RPE_PATTERN.sub("", value)).strip(" -")
    pieces = [clean_text(piece) for piece in re.split(r"\s+-\s+", without_rpe)]
    kept: list[str] = []
    for piece in pieces:
        lower = piece.lower()
        if not piece:
            continue
        if (
            "load" in lower
            or "weight" in lower
            or re.search(r"\b(?:add|use)\s+(?:db|dumbbell)\b", lower)
            or re.search(r"\bkg\b", lower)
        ):
            continue
        kept.append(piece)
    return rpe, f" {BULLET} ".join(kept).strip(f" {BULLET}")


def append_v2_note(exercise: dict, raw: str) -> None:
    rpe, note = clean_v2_note(raw)
    if rpe:
        exercise["rpe"] = rpe
    if note:
        existing = exercise.get("note", "")
        exercise["note"] = (
            f"{existing} {BULLET} {note}" if existing and note not in existing else note or existing
        )


def v2_week_number(path: Path) -> int:
    match = re.search(r"Week\s+(\d+)", path.stem, flags=re.I)
    if not match:
        raise ValueError(f"Could not determine the week number from {path.name}")
    return int(match.group(1))


def v2_week_rpe(sessions: list[dict]) -> str:
    values = sorted(
        {
            int(number)
            for session in sessions
            for section in session["sections"]
            for exercise in section["exercises"]
            if (match := RPE_PATTERN.search(exercise.get("rpe", "")))
            for number in re.findall(r"\d+", match.group(1))
        }
    )
    if not values:
        return ""
    return f"RPE {values[0]}" if len(values) == 1 else f"RPE {values[0]}-{values[-1]}"


def parse_base_v2(source_dir: Path) -> dict:
    """Extract the 12 TeamBuildr PDFs into the same app model as the DOCX plans."""
    if not source_dir.is_dir():
        raise FileNotFoundError(
            f"Base Builder V2 folder was not found: {source_dir}. "
            "Set BASE_BUILDER_V2_DIR before rebuilding the data."
        )

    files = sorted(source_dir.glob("*.pdf"), key=v2_week_number)
    if len(files) != PROGRAM_META["base-v2"]["weeks"]:
        raise ValueError(f"base-v2: expected 12 PDFs, found {len(files)}")

    stage_labels = ("Foundation", "Build", "Peak", "Deload")
    weeks: list[dict] = []
    for expected_number, path in enumerate(files, start=1):
        week_number = v2_week_number(path)
        if week_number != expected_number:
            raise ValueError(f"base-v2: expected Week {expected_number}, found Week {week_number}")

        sessions: list[dict] = []
        current_session: dict | None = None
        current_identity = ""
        current_section: dict | None = None
        last_exercise: dict | None = None

        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    for raw_row in table:
                        cells = [clean_text(cell or "") for cell in raw_row]
                        row_text = clean_text(" ".join(cell for cell in cells if cell))
                        if not row_text:
                            continue

                        day_match = V2_DAY_HEADING.match(row_text)
                        if day_match:
                            if current_identity != row_text:
                                current_identity = row_text
                                current_session = {
                                    "id": f"base-v2-w{week_number:02d}-s{len(sessions) + 1}",
                                    "label": f"Session {len(sessions) + 1}",
                                    "sections": [],
                                }
                                sessions.append(current_session)
                                current_section = None
                                last_exercise = None
                            continue

                        if not current_session:
                            continue

                        heading = v2_section_title(row_text)
                        if heading:
                            if current_section and current_section["title"] == heading:
                                last_exercise = None
                                continue
                            current_section = {
                                "id": f"{current_session['id']}-section-{len(current_session['sections']) + 1}",
                                "title": heading,
                                "exercises": [],
                            }
                            current_session["sections"].append(current_section)
                            last_exercise = None
                            continue

                        if not current_section:
                            continue

                        first_cell = cells[0] if cells else ""
                        if not first_cell:
                            if re.fullmatch(r"(?:result|reps|set\s*\d+|\s)+", row_text, flags=re.I):
                                continue
                            if last_exercise:
                                append_v2_note(last_exercise, row_text)
                            continue

                        upper = first_cell.upper()
                        if upper in {"WORKOUT", "NOTE", "DISCLAIMER", "DONALD SIBLEY"}:
                            continue
                        if "SET 1" in upper or "RESULT" in upper:
                            continue

                        values = v2_prescription_values(cells)
                        if not values:
                            continue
                        name = re.sub(r"^[WABCD]\s+", "", first_cell, flags=re.I)
                        exercise = {
                            "name": name,
                            "prescription": prescription(values),
                        }
                        current_section["exercises"].append(exercise)
                        last_exercise = exercise

        if len(sessions) != 3:
            raise ValueError(f"base-v2 Week {week_number}: expected 3 sessions, found {len(sessions)}")
        for session in sessions:
            if not session["sections"] or any(not section["exercises"] for section in session["sections"]):
                raise ValueError(f"{session['id']}: an exercise section is empty")

        phase = ((week_number - 1) // 4) + 1
        stage = stage_labels[(week_number - 1) % 4]
        weeks.append(
            {
                "number": week_number,
                "focus": f"Phase {phase} - {stage}",
                "rpe": v2_week_rpe(sessions),
                "sessions": sessions,
            }
        )

    return {"id": "base-v2", "title": PROGRAM_META["base-v2"]["title"], "weeks": weeks}


def parse_teambuildr_sessions(program_id: str, week_number: int, path: Path) -> list[dict]:
    """Extract three dated TeamBuildr tables as date-free app sessions."""
    sessions: list[dict] = []
    current_session: dict | None = None
    current_identity = ""
    current_section: dict | None = None
    last_exercise: dict | None = None

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for raw_row in table:
                    cells = [clean_text(cell or "") for cell in raw_row]
                    row_text = clean_text(" ".join(cell for cell in cells if cell))
                    if not row_text:
                        continue

                    if V2_DAY_HEADING.match(row_text):
                        if current_identity != row_text:
                            current_identity = row_text
                            current_session = {
                                "id": f"{program_id}-w{week_number:02d}-s{len(sessions) + 1}",
                                "label": f"Session {len(sessions) + 1}",
                                "sections": [],
                            }
                            sessions.append(current_session)
                            current_section = None
                            last_exercise = None
                        continue

                    if not current_session:
                        continue

                    heading = v2_section_title(row_text)
                    if heading:
                        if current_section and current_section["title"] == heading:
                            last_exercise = None
                            continue
                        current_section = {
                            "id": f"{current_session['id']}-section-{len(current_session['sections']) + 1}",
                            "title": heading,
                            "exercises": [],
                        }
                        current_session["sections"].append(current_section)
                        last_exercise = None
                        continue

                    if not current_section:
                        continue

                    first_cell = cells[0] if cells else ""
                    if not first_cell:
                        if re.fullmatch(r"(?:result|reps|set\s*\d+|\s)+", row_text, flags=re.I):
                            continue
                        if last_exercise:
                            append_v2_note(last_exercise, row_text)
                        continue

                    upper = first_cell.upper()
                    if upper in {"WORKOUT", "NOTE", "DISCLAIMER", "DONALD SIBLEY"}:
                        continue
                    if "SET 1" in upper or "RESULT" in upper:
                        continue

                    values = v2_prescription_values(cells)
                    if not values:
                        continue
                    name = re.sub(r"^[WABCD]\s+", "", first_cell, flags=re.I)
                    exercise = {
                        "name": name,
                        "prescription": prescription(values),
                    }
                    current_section["exercises"].append(exercise)
                    last_exercise = exercise

    if len(sessions) != 3:
        raise ValueError(f"{program_id} Week {week_number}: expected 3 sessions, found {len(sessions)}")
    for session in sessions:
        if not session["sections"] or any(not section["exercises"] for section in session["sections"]):
            raise ValueError(f"{session['id']}: an exercise section is empty")
    return sessions


def race_source_date(path: Path) -> tuple[int, int, int]:
    """Read a PDF's first schedule heading solely to order the weekly files."""
    with pdfplumber.open(path) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
    match = RACE_SOURCE_DATE.search(first_page_text)
    if not match:
        raise ValueError(f"Could not determine the schedule date in {path.name}")
    month, day, year = match.groups()
    return int(year), RACE_MONTHS[month.upper()], int(day)


def parse_race_builder(source_dir: Path) -> dict:
    """Rebuild Race Builder directly from the supplied 12 build and 2 recovery PDFs."""
    if not source_dir.is_dir():
        raise FileNotFoundError(
            f"Race Builder folder was not found: {source_dir}. "
            "Set RACE_BUILDER_DIR before rebuilding the data."
        )

    dated_files = sorted(
        ((race_source_date(path), path) for path in source_dir.glob("*.pdf")),
        key=lambda item: item[0],
    )
    expected_weeks = PROGRAM_META["race"]["weeks"]
    if len(dated_files) != expected_weeks:
        raise ValueError(f"race: expected {expected_weeks} PDFs, found {len(dated_files)}")
    if len({source_date for source_date, _ in dated_files}) != expected_weeks:
        raise ValueError("race: PDFs do not have unique weekly schedule dates")

    weeks: list[dict] = []
    for week_number, (_, path) in enumerate(dated_files, start=1):
        sessions = parse_teambuildr_sessions("race", week_number, path)
        weeks.append(
            {
                "number": week_number,
                "focus": "Build" if week_number <= 12 else "Recovery",
                "rpe": v2_week_rpe(sessions),
                "sessions": sessions,
            }
        )

    return {"id": "race", "title": PROGRAM_META["race"]["title"], "weeks": weeks}


def assert_clean(data: dict) -> None:
    """Fail rather than leaking a source date, weekday, or load value to the app."""
    serialized = json.dumps(data, ensure_ascii=False).lower()
    forbidden = [
        (r"\bload\b", "load"),
        (r"\bweight\b", "weight reference"),
        (r"\b(?:sunday|monday|tuesday|wednesday|thursday|friday|saturday)\b", "weekday"),
        (r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d", "date"),
        (r"\bkg\b", "weight unit"),
        (r"\bmax\s+\d", "numeric max"),
    ]
    for pattern, label in forbidden:
        if re.search(pattern, serialized, flags=re.I):
            raise ValueError(f"Generated data still contains {label}")
    if "rpe" not in serialized:
        raise ValueError("Generated data unexpectedly contains no RPE values")


def main() -> None:
    programs = {program_id: parse_program(program_id, path) for program_id, path in SOURCES.items()}
    programs["base-v2"] = parse_base_v2(V2_SOURCE_DIR)
    programs["race"] = parse_race_builder(RACE_SOURCE_DIR)
    assert_clean(programs)
    payload = "/* Generated from the supplied plans. Run build_program_data.py to refresh. */\n"
    payload += f"const PROGRAMS = {json.dumps(programs, ensure_ascii=False, separators=(',', ':'))};\n"
    OUTPUT_PATH.write_text(payload, encoding="utf-8")
    session_count = sum(len(week["sessions"]) for program in programs.values() for week in program["weeks"])
    print(f"Wrote {OUTPUT_PATH.name} with {session_count} sessions.")


if __name__ == "__main__":
    main()
