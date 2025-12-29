#!/usr/bin/env python3
import csv
import random
import html
import string
from pathlib import Path

BASE_DIR = Path(__file__).parent

TARGET_FOLDERS = [
    "SRC_Gesamtfragenkatalog",
    "UBI_Ergaenzungsfragenkatalog",
    "UBI_Gesamtfragenkatalog",
    "FKN_Fachkundenachweis",
]

IN_DELIMITER = ";"
OUT_DELIMITER = ";"


# ---------- HELPERS ----------

def normalize(s):
    if s is None:
        return ""
    return str(s).strip()


def normkey(k: str) -> str:
    k = normalize(k).lower()
    k = k.replace("\ufeff", "")
    k = k.replace("_", " ")
    k = " ".join(k.split())
    return k


def pick(row, *keys):
    norm_map = {normkey(k): k for k in row.keys() if k is not None}
    for want in keys:
        actual = norm_map.get(normkey(want))
        if actual is not None:
            return row.get(actual)
    return None


def matchkey(s: str) -> str:
    s = normalize(s)
    s = s.replace("\u00a0", " ")
    s = " ".join(s.split())
    return s


# ---------- HTML BUILDERS ----------

def build_front_html(question, options):
    q = html.escape(question).replace("\n", "<br>")

    parts = [
        "<div style='text-align:left;'>",
        f"<div style='font-weight:700; margin-bottom:8px;'>{q}</div>",
    ]

    if options:
        parts.append("<div>")
        for i, opt in enumerate(options):
            letter = string.ascii_uppercase[i]
            parts.append(
                "<div style='margin:2px 0;'>"
                f"<span style='display:inline-block; width:24px;'>{letter}.</span>"
                f"<span>{html.escape(opt)}</span>"
                "</div>"
            )
        parts.append("</div>")

    parts.append("</div>")
    return "".join(parts)


def build_back_html(correct_letters, correct_texts):
    letters = ", ".join(correct_letters)
    answers_html = "".join(
        f"<div style='margin-top:4px;'>{html.escape(t).replace(chr(10), '<br>')}</div>"
        for t in correct_texts
    )

    return (
        "<div style='text-align:left;'>"
        f"<div style='margin-top:8px;'><b>Richtige Antwort:</b> {html.escape(letters)}</div>"
        f"{answers_html}"
        "</div>"
    )


# ---------- CSV HANDLING ----------

def read_csv(path: Path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=IN_DELIMITER))


def process_row(row):
    question = normalize(pick(row, "Frage", "Question"))
    a = normalize(pick(row, "Antwort A"))
    b = normalize(pick(row, "Antwort B"))
    c = normalize(pick(row, "Antwort C"))
    d = normalize(pick(row, "Antwort D"))
    correct_raw = normalize(pick(row, "Richtige Antwort"))

    if not question:
        return None, "missing_question"

    raw_options = [a, b, c, d]
    options = [opt for opt in raw_options if opt]

    # --- Freitextfrage ---
    if len(options) == 0:
        if not correct_raw:
            return None, "missing_correct_answer"
        front = build_front_html(question, [])
        back = (
            "<div style='text-align:left;'>"
            "<div style='margin-top:8px;'><b>Antwort:</b></div>"
            f"<div style='margin-top:4px;'>{html.escape(correct_raw).replace(chr(10), '<br>')}</div>"
            "</div>"
        )
        return (front, back), None

    # --- Multiple Choice ---
    if len(options) < 2:
        return None, "not_enough_options"

    if not correct_raw:
        return None, "missing_correct_answer"

    parts = [p.strip() for p in correct_raw.split("|") if p.strip()]
    if not parts:
        return None, "missing_correct_answer"

    option_key_to_text = {matchkey(opt): opt for opt in options}
    correct_keys = [matchkey(p) for p in parts]

    if any(k not in option_key_to_text for k in correct_keys):
        return None, "correct_answer_not_found"

    indexed = list(enumerate(options))
    random.shuffle(indexed)

    shuffled_options = [o for _, o in indexed]

    correct_letters = []
    correct_texts = []
    correct_key_set = set(correct_keys)

    for i, (_, opt_text) in enumerate(indexed):
        if matchkey(opt_text) in correct_key_set:
            correct_letters.append(string.ascii_uppercase[i])
            correct_texts.append(opt_text)

    if not correct_letters:
        return None, "correct_answer_not_found"

    front = build_front_html(question, shuffled_options)
    back = build_back_html(correct_letters, correct_texts)

    return (front, back), None


# ---------- MAIN ----------

def process_folder(folder_name: str):
    folder = BASE_DIR / folder_name
    out_file = folder / f"ANKI-IMPORT__{folder_name}.csv"
    skip_file = folder / f"SKIPPED__{folder_name}.csv"

    # NEW: delete old output files if they exist
    if out_file.exists():
        out_file.unlink()
    if skip_file.exists():
        skip_file.unlink()

    cards = []
    skipped = []

    rows_seen = 0
    files_seen = 0

    for csv_file in sorted(folder.glob("*.csv")):
        if csv_file.name.startswith(("MASTER__", "SKIPPED__", "ANKI-IMPORT__")):
            continue

        files_seen += 1
        rows = read_csv(csv_file)

        for idx, row in enumerate(rows, start=2):
            rows_seen += 1
            card, reason = process_row(row)

            if card:
                cards.append(card)
            else:
                skipped.append({
                    "file": csv_file.name,
                    "row": idx,
                    "reason": reason,
                    "question": normalize(pick(row, "Frage", "Question"))
                })

    with open(out_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=OUT_DELIMITER, quoting=csv.QUOTE_ALL)
        writer.writerows(cards)

    if skipped:
        with open(skip_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["file", "row", "reason", "question"],
                delimiter=OUT_DELIMITER,
                quoting=csv.QUOTE_ALL,
            )
            writer.writeheader()
            writer.writerows(skipped)

    print(
        f"[OK] {folder_name}: files={files_seen}, "
        f"rows_seen={rows_seen}, cards={len(cards)}, skipped={len(skipped)}"
    )

    return rows_seen, len(cards), len(skipped)


def main():
    total_rows = total_cards = total_skipped = 0

    for folder in TARGET_FOLDERS:
        r, c, s = process_folder(folder)
        total_rows += r
        total_cards += c
        total_skipped += s

    print(
        f"Done. Total rows: {total_rows}, "
        f"cards written: {total_cards}, skipped: {total_skipped}"
    )


if __name__ == "__main__":
    main()
