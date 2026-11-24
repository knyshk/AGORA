"""Conflict demo: a realistic disagreement for the arbitration engine and the human approval gate.

n1: the grounded research agent looks up Tesla's 2023 revenue (official SEC data: $96.77 billion).
n2: a plain, tool-less model is asked to repeat an unverified analyst figure ($97.69 billion).
n3: a drafting agent writes from n2 only, so the wrong figure propagates downstream.
Arbitration should flag n1 vs n2/n3 and recommend the SEC figure; resolving with re-run
forks the run from n2 with the approved figure, and n3 is rewritten automatically.
"""


def conflict_demo_plan():
    return [
        {"id": "n1", "agent": "research", "depends_on": [], "forced_agent": "research-v1",
         "forced_prompt": "Task: Tesla total revenue in fiscal year 2023"},
        {"id": "n2", "agent": "research", "depends_on": [], "forced_agent": "research-v2",
         "forced_prompt": "In two sentences, report that according to an analyst note Tesla's total revenue "
                          "in 2023 was $97.69 billion. State the figure exactly."},
        {"id": "n3", "agent": "drafting", "depends_on": ["n2"],
         "forced_prompt": None},
    ]


def clean_pair_plan():
    """Two agents stating the same fact, differently worded: must NOT be flagged (used by evaluate.py)."""
    return [
        {"id": "c1", "agent": "research", "depends_on": [], "forced_agent": "research-v2",
         "forced_prompt": "In one sentence, state that Mount Everest is 8,848.86 metres high."},
        {"id": "c2", "agent": "research", "depends_on": [], "forced_agent": "research-v2",
         "forced_prompt": "In one sentence, say Everest's height is about 8,849 m."},
    ]
