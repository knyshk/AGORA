"""Shared numeric grounding: is a number actually present in the source text?
Used by the chart agent (drop invented data points) and the drafting agent
(flag invented numbers in the prose)."""
import re

REL_TOLERANCE = 0.01
MIN_SIG_DIGITS_FOR_SCALING = 3
UNIT_SCALES = (1, 1e3, 1e-3, 1e6, 1e-6, 1e9, 1e-9, 1e12, 1e-12)


def context_numbers(text: str) -> list:
    text = re.sub(r"\[\d+\]|【\d+】", " ", text)  # citation markers are not data
    nums = []
    for m in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        try:
            nums.append(float(m.replace(",", "")))
        except ValueError:
            continue
    return nums


def significant_digits(n: float) -> int:
    return len(f"{n:.6g}".replace(".", "").replace("-", "").lstrip("0").split("e")[0].rstrip("0"))


def is_grounded(value: float, numbers: list) -> bool:
    """Exact match (within rounding), or a unit-scaled match against a number precise
    enough (3+ significant digits) that the match cannot be a coincidence like 1 -> 1000."""
    if value == 0:
        return 0.0 in numbers
    target = abs(value)
    for n in numbers:
        scales = UNIT_SCALES if significant_digits(n) >= MIN_SIG_DIGITS_FOR_SCALING else (1,)
        for scale in scales:
            candidate = n * scale
            if candidate and abs(candidate - target) / target <= REL_TOLERANCE:
                return True
    return False


# ---- unit consistency (a chart must not mix "96.77 billion" with "176,191 million") ----
UNIT_WORDS = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12,
              "mn": 1e6, "bn": 1e9, "tn": 1e12, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
MULTIPLIERS = (1.0, 1e3, 1e6, 1e9, 1e12)
UNIT_NAMES = {1.0: "plain units", 1e3: "thousands", 1e6: "millions", 1e9: "billions", 1e12: "trillions"}
_QUANTITY = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)(?:\s*(thousand|million|billion|trillion|mn|bn|tn)\b|([KMBT])\b)?", re.I)


def context_quantities(text: str) -> list:
    """Absolute values of the numbers in the text, applying unit words ("176,191 million" -> 1.76191e11).
    Single-letter suffixes count only in upper case and attached ("96.8B"), so "8,848 m" stays metres."""
    text = re.sub(r"\[\d+\]|【\d+】", " ", text)
    out = []
    for raw, word, letter in _QUANTITY.findall(text):
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        mult = UNIT_WORDS.get(word.lower(), 1.0) if word else (UNIT_WORDS.get(letter, 1.0) if letter.isupper() else 1.0)
        out.append(value * mult)
    return out


def implied_multipliers(value: float, quantities: list) -> set:
    """Which unit (1, thousand, million, ...) the value must be read in to match the text."""
    if not value:
        return set()
    return {m for m in MULTIPLIERS
            if any(q and abs(value * m - q) <= REL_TOLERANCE * abs(q) for q in quantities)}


def shared_unit(values: list, text: str):
    """(multiplier, per-value units). multiplier is None when the values cannot all be one unit."""
    quantities = context_quantities(text)
    per_value = {v: implied_multipliers(v, quantities) for v in values}
    constrained = [s for s in per_value.values() if s]
    if not constrained:
        return 1.0, per_value
    common = set.intersection(*constrained)
    return (max(common) if common else None), per_value
