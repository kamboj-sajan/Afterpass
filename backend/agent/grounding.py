"""Checks an answer against the tool results behind it (project rule: never invent numbers).

Every number in the answer must be a number that appears in that turn's tool results or in
the question, to within one unit of the last digit the answer gives, and allowing for lakh,
crore and thousand. This is a mechanical
check: it catches invented figures, not a true figure used for the wrong thing.
"""

from __future__ import annotations

import json
import re

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
# Names that contain digits and are not figures.
NOT_FIGURES = re.compile(r"PM\s?2\.5|Sentinel[\s\-\u2010-\u2015]?2|CO2|H3", re.IGNORECASE)
# Thin and no-break spaces used to group thousands ("53 620").
GROUPING_SPACE = re.compile(r"(?<=\d)[\u00a0\u2009\u202f](?=\d{3}(?!\d))")
UNITS = (
    (re.compile(r"^\s*(lakh|lac|लाख)", re.IGNORECASE), 1e5),
    (re.compile(r"^\s*(crore|करोड़|करोड)", re.IGNORECASE), 1e7),
    (re.compile(r"^\s*(thousand|हज़ार|हजार)", re.IGNORECASE), 1e3),
)
# Words the project never uses about farmers or fires (brief §14.4).
BANNED = re.compile(r"\b(illegal|hidden|caught)\b|अवैध|गैरकानूनी|ग़ैरक़ानूनी", re.IGNORECASE)


def _clean(text: str) -> str:
    text = GROUPING_SPACE.sub("", text.translate(DEVANAGARI_DIGITS))
    return NOT_FIGURES.sub(" ", text)


def figures(text: str) -> list[tuple[str, float, int]]:
    """Numbers in a text as (as written, value, decimal places), scaled by lakh or crore."""
    found = []
    text = _clean(text)
    for match in NUMBER.finditer(text):
        raw = match.group().rstrip(",")
        plain = raw.replace(",", "")
        value = float(plain)
        decimals = len(plain.partition(".")[2])
        written = raw
        for pattern, scale in UNITS:
            unit = pattern.match(text[match.end() :])
            if unit:
                value, decimals, written = value * scale, -1, f"{raw} {unit.group(1)}"
                break
        found.append((written, value, decimals))
    return found


def _matches(value: float, decimals: int, allowed: list[float]) -> bool:
    for known in allowed:
        # Rounded or cut off at the precision the answer uses: within one unit of its last digit.
        if decimals >= 0 and abs(known - value) < 10**-decimals:
            return True
        # Scaled figures ("4.24 lakh") and large rounded ones ("about 4,24,000").
        if (decimals < 0 or value >= 1000) and known and abs(value - known) <= 0.01 * abs(known):
            return True
    return False


def check(answer: str, question: str, results: list[dict]) -> dict:
    """Which numbers in the answer are backed by the tool results or the question."""
    # Line breaks inside tool text arrive escaped; unescape them so "\n0.5" reads as 0.5.
    source = json.dumps(results, ensure_ascii=False).replace("\\n", " ") + " " + question
    allowed = [value for _, value, _ in figures(source)]
    # The same facts said another way: "4 PM" for 16:00, "12" for midnight, "2024-25".
    allowed += [value - 12 for value in allowed if 13 <= value <= 23 and value == int(value)]
    allowed += [12.0] if 0.0 in allowed else []
    allowed += [value % 100 for value in allowed if 1900 <= value <= 2100 and value == int(value)]
    seen = figures(answer)
    unmatched = [
        written for written, value, decimals in seen if not _matches(value, decimals, allowed)
    ]
    wording = sorted({match.group().lower() for match in BANNED.finditer(answer)})
    return {
        "grounded": not unmatched and not wording,
        "numbers": len(seen),
        "unmatched": unmatched,
        "banned_words": wording,
    }
