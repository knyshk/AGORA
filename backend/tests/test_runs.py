import time
from db.database import init_db
from db.recorder import RunRecorder
from db import crud


async def test_run_is_saved_with_events_and_nodes():
    init_db()
    started = time.time()
    run_id = crud.create_run("test query")
    rec = RunRecorder(run_id)
    await rec("plan_created", {"plan": [{"id": "n1", "agent": "research", "depends_on": []}]})
    await rec("node_started", {"node_id": "n1", "skill": "research", "depends_on": []})
    await rec("node_finished", {"node_id": "n1", "skill": "research", "agent": "research-v1",
                                "attempts": 1, "duration_s": 1.2, "error": None, "output": "hello"})
    crud.finish_run(run_id, [{"id": "n1"}], "complete", [], started)

    data = crud.get_run(run_id)
    assert data["run"]["status"] == "complete"
    assert [e["type"] for e in data["events"]] == ["plan_created", "node_started", "node_finished"]
    assert data["nodes"][0]["status"] == "done"
    assert data["nodes"][0]["output"] == "hello"
    assert any(r["id"] == run_id for r in crud.list_runs())


def test_unknown_run_returns_none():
    init_db()
    assert crud.get_run("does-not-exist") is None

async def test_two_recorders_on_one_run_never_reuse_a_sequence_number():
    init_db()
    run_id = crud.create_run("q")
    executor_log, api_log = RunRecorder(run_id), RunRecorder.resume(run_id)
    await executor_log("node_started", {"node_id": "n1", "skill": "research", "depends_on": []})
    await api_log("node_paused", {"node_id": "n2"})          # a person acts while the run is going
    await executor_log("node_started", {"node_id": "n2", "skill": "drafting", "depends_on": []})
    seqs = [e["seq"] for e in crud.get_run(run_id)["events"]]
    assert seqs == [1, 2, 3]
