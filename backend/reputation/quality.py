"""Grade a node's output quality in [0, 1] from the checks each agent already reports.

This replaces "no exception = success". Every grade comes with a plain-language reason,
which is stored in the event log and shown in the UI.
"""
import re

NEUTRAL = 0.6  # output with no machine-checkable signal (e.g. plain baseline agents)


def _research(out: str):
    if out.startswith("NOTE: no live sources"):
        return 0.3, "no live sources retrieved; answer is unverified model knowledge"
    if "\nSources\n" not in out:
        return NEUTRAL, "plain answer without retrieved sources"
    missing = out.lower().count("not found in sources")
    if missing:
        return max(0.4, 1.0 - 0.15 * missing), f"cited answer, {missing} part(s) not found in sources"
    return 1.0, "cited answer, all parts found in sources"


def _chart(out: str):
    kept = re.search(r"All (\d+) values were checked", out)
    if not kept:
        return NEUTRAL, "no validated chart spec"
    k = int(kept.group(1))
    dropped = re.search(r"Removed (\d+) value", out)
    d = int(dropped.group(1)) if dropped else 0
    return k / (k + d), f"{k} grounded value(s), {d} invented value(s) removed"


def _drafting(out: str):
    if "Citation check: passed" in out:
        return 1.0, "citation check passed"
    if "Citation check: NOT fully passed" in out:
        return 0.4, "citation check failed after retry"
    if "draft is uncited" in out:
        return 0.5, "no sources available to cite"
    return NEUTRAL, "no citation check"


def fact_check_counts(out: str):
    m = re.search(r"(\d+) supported, (\d+) unsupported, (\d+) contradicted, (\d+) unverifiable", out)
    return tuple(int(x) for x in m.groups()) if m else None


def _fact_check(out: str):
    counts = fact_check_counts(out)
    if counts is None:
        return 0.5, "no claims could be checked"
    total = sum(counts)
    if total == 0:
        return 0.5, "no claims could be checked"
    verifiable = total - counts[3]
    return verifiable / total, f"verified {verifiable}/{total} claims against their sources"


GRADERS = {"research": _research, "chart": _chart, "drafting": _drafting, "fact_check": _fact_check}


def assess(skill: str, output: str) -> tuple:
    grader = GRADERS.get(skill)
    if grader is None or not isinstance(output, str):
        return NEUTRAL, "no grader for this skill"
    q, reason = grader(output)
    return round(q, 3), reason


def draft_feedback(fact_check_output: str):
    """Quality evidence for the DRAFTING agent from the fact-check verdicts on its claims."""
    counts = fact_check_counts(fact_check_output)
    if not counts:
        return None
    supported, unsupported, contradicted, _ = counts
    judged = supported + unsupported + contradicted
    if judged == 0:
        return None
    q = (supported + 0.25 * unsupported) / judged  # unsupported is weak evidence; contradicted is none
    return round(q, 3), f"fact-check: {supported}/{judged} of its claims supported, {contradicted} contradicted"
