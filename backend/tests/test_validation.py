import pytest
from orchestration.validation import validate_plan, PlanError

AGENTS = {"research": "", "drafting": "", "chart": "", "fact_check": ""}


def test_valid_plan_passes():
    plan = [
        {"id": "n1", "agent": "research", "depends_on": []},
        {"id": "n2", "agent": "drafting", "depends_on": ["n1"]},
        {"id": "n3", "agent": "chart", "depends_on": ["n1"]},
        {"id": "n4", "agent": "fact_check", "depends_on": ["n2", "n3"]},
    ]
    assert validate_plan(plan, AGENTS) == plan


def test_empty_plan_rejected():
    with pytest.raises(PlanError):
        validate_plan([], AGENTS)


def test_unknown_agent_rejected():
    with pytest.raises(PlanError):
        validate_plan([{"id": "n1", "agent": "magic", "depends_on": []}], AGENTS)


def test_unknown_dependency_rejected():
    with pytest.raises(PlanError):
        validate_plan([{"id": "n1", "agent": "research", "depends_on": ["zz"]}], AGENTS)


def test_duplicate_id_rejected():
    plan = [
        {"id": "n1", "agent": "research", "depends_on": []},
        {"id": "n1", "agent": "drafting", "depends_on": []},
    ]
    with pytest.raises(PlanError):
        validate_plan(plan, AGENTS)


def test_cycle_rejected():
    plan = [
        {"id": "a", "agent": "research", "depends_on": ["b"]},
        {"id": "b", "agent": "drafting", "depends_on": ["a"]},
    ]
    with pytest.raises(PlanError):
        validate_plan(plan, AGENTS)


def test_self_dependency_rejected():
    with pytest.raises(PlanError):
        validate_plan([{"id": "a", "agent": "research", "depends_on": ["a"]}], AGENTS)