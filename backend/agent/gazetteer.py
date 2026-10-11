"""Finds districts and Delhi localities by name: English, Hindi and common misspellings."""

from __future__ import annotations

import unicodedata

from rapidfuzz import fuzz, process

# Other spellings people use for the published districts, English and Hindi.
DISTRICT_ALIASES: dict[str, tuple[str, ...]] = {
    "Sangrur": ("Sangroor", "संगरूर"),
    "Bathinda": ("Bhatinda", "बठिंडा", "भटिंडा"),
    "Firozpur": ("Ferozepur", "Firozepur", "Ferozpur", "फ़िरोज़पुर", "फिरोजपुर"),
}
MIN_SCORE = 82


def fold(text: str) -> str:
    """Lower-case text without spaces, punctuation or the Devanagari nukta."""
    text = unicodedata.normalize("NFD", text).replace("़", "")
    text = unicodedata.normalize("NFC", text).casefold()
    return "".join(ch for ch in text if ch.isalnum() or unicodedata.category(ch).startswith("M"))


# Words people add around a district's name.
DISTRICT_WORDS = ("district", "zila", "jila", "ज़िला", "जिला", "ज़िले", "जिले")


def find_district(name: str, districts: list[str]) -> str | None:
    """The published district a name refers to, or None."""
    for word in DISTRICT_WORDS:
        name = name.replace(word, " ").replace(word.title(), " ")
    wanted = fold(name)
    if not wanted:
        return None
    names = {fold(district): district for district in districts}
    for district in districts:
        for alias in DISTRICT_ALIASES.get(district, ()):
            names[fold(alias)] = district
    if wanted in names:
        return names[wanted]
    match = process.extractOne(wanted, list(names), scorer=fuzz.ratio, score_cutoff=MIN_SCORE)
    return None if match is None else names[match[0]]


def find_locality(name: str, localities: list[dict]) -> tuple[dict | None, list[str]]:
    """The Delhi locality a name refers to, and other close names to offer when unsure.

    An exact match on the English or Hindi name wins, then a known name inside a longer
    phrase ("Dwarka sector 10"), then the closest spelling. Where several places share the
    name, one that also has a Hindi name is preferred (these are the well-known areas).
    """
    wanted = fold(name)
    if not wanted:
        return None, []
    by_key: dict[str, list[dict]] = {}
    for item in localities:
        for text in (item["name"], item.get("name_hi") or ""):
            if text:
                by_key.setdefault(fold(text), []).append(item)

    def best(key: str) -> dict:
        return sorted(by_key[key], key=lambda item: (not item.get("name_hi"), item["id"]))[0]

    if wanted in by_key:
        return best(wanted), []
    inside = [key for key in by_key if len(key) >= 5 and key in wanted]
    if inside:
        return best(max(inside, key=len)), []
    close = process.extract(wanted, list(by_key), scorer=fuzz.ratio, score_cutoff=70, limit=6)
    names: list[str] = []
    for key, _, _ in close:
        if best(key)["name"] not in names:
            names.append(best(key)["name"])
    if close and close[0][1] >= MIN_SCORE:
        return best(close[0][0]), names[1:]
    return None, names
