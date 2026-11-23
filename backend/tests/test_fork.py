from orchestration.fork import descendants, reusable_outputs

PLAN = [
    {"id": "n1", "agent": "research", "depends_on": []},
    {"id": "n2", "agent": "drafting", "depends_on": ["n1"]},
    {"id": "n3", "agent": "chart", "depends_on": ["n1"]},
    {"id": "n4", "agent": "fact_check", "depends_on": ["n2", "n3"]},
]


def test_descendants_of_chart_node():
    assert descendants(PLAN, "n3") == {"n3", "n4"}


def test_descendants_of_root_is_everything():
    assert descendants(PLAN, "n1") == {"n1", "n2", "n3", "n4"}


def test_reusable_outputs_keep_unaffected_nodes():
    outputs = {"n1": "r", "n2": "d", "n3": "c", "n4": "f"}
    assert reusable_outputs(PLAN, outputs, "n3") == {"n1": "r", "n2": "d"}