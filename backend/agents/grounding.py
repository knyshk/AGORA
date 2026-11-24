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
