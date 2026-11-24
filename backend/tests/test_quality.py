from reputation.quality import assess, draft_feedback, NEUTRAL


def test_research_grades():
    assert assess("research", "NOTE: no live sources could be retrieved. x")[0] == 0.3
    assert assess("research", "Answer [1].\n\n---\nSources\n[1] a - http://a")[0] == 1.0
    q, reason = assess("research", "X not found in sources.\n\n---\nSources\n[1] a - http://a")
    assert q == 0.85 and "1 part" in reason
    assert assess("research", "plain text answer")[0] == NEUTRAL


def test_chart_grade_is_grounded_fraction():
    out = "All 3 values were checked against the numbers.\nRemoved 1 value(s) not found in the context: x."
    assert assess("chart", out)[0] == 0.75
    assert assess("chart", "All 4 values were checked")[0] == 1.0


def test_drafting_grades():
    assert assess("drafting", "...\nCitation check: passed. 3 figure(s)")[0] == 1.0
    assert assess("drafting", "...\nCitation check: NOT fully passed. x")[0] == 0.4


def test_fact_check_grade_and_draft_feedback():
    out = "**Fact check: 10 cited claim(s)** — 6 supported, 2 unsupported, 1 contradicted, 1 unverifiable."
    assert assess("fact_check", out)[0] == 0.9
    q, reason = draft_feedback(out)
    assert q == round((6 + 0.5) / 9, 3)
    assert "1 contradicted" in reason
    assert draft_feedback("no table here") is None


def test_unknown_skill_is_neutral():
    assert assess("planner", "anything")[0] == NEUTRAL
