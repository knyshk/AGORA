def conflict_demo_plan():
    return [
        {
            "id": "a",
            "agent": "research",
            "depends_on": [],
            "forced_prompt": "State in one sentence that Q3 revenue was exactly $4.1 million. Say this clearly and directly.",
        },
        {
            "id": "b",
            "agent": "fact_check",
            "depends_on": [],
            "forced_prompt": "State in one sentence that Q3 revenue was exactly $4.6 million. Say this clearly and directly.",
        },
    ]
def clean_pair_plan():
    """Two agents stating the same fact, differently worded — should NOT be flagged."""
    return [
        {
            "id": "c1",
            "agent": "research",
            "depends_on": [],
            "forced_prompt": "In one sentence, state that Paris is the capital of France.",
        },
        {
            "id": "c2",
            "agent": "fact_check",
            "depends_on": [],
            "forced_prompt": "In one sentence, confirm that the capital city of France is Paris.",
        },
    ]