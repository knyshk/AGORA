import io
import time

from docx import Document
from fastapi.testclient import TestClient

from agents import chart_tools, factcheck_tools
from db import crud
from db.database import init_db
from db.recorder import RunRecorder
from reports import builder

DRAFT = ("## Revenue\nTesla earned **$96.77 billion** in 2023 [1].\n\n| Company | Revenue |\n|---|---|\n| Tesla | 96.77 [1] |\n\n"
         "---\nSources\n[1] SEC EDGAR 10-K data: Tesla - https://data.sec.gov/x.json\n\nCitation check: passed. 1 figure(s)")


async def _run():
    init_db()
    data = {"title": "Revenue 2023", "chart_type": "bar", "x_label": "Company", "y_label": "Revenue", "unit": "USD billions",
            "data": [{"category": "Tesla", "value": 96.77}]}
    chart = chart_tools.render_output(data, chart_tools.build_spec(data), [])
    fc = factcheck_tools.render([{"id": 1, "text": "Tesla earned $96.77 billion in 2023 [1]", "sources": [1]}],
                                {1: {"verdict": "supported", "quote": "$96.77 billion", "note": ""}}, {1: ("t", "u")})
    plan = [{"id": "n1", "agent": "drafting", "depends_on": []}, {"id": "n2", "agent": "chart", "depends_on": []},
            {"id": "n3", "agent": "fact_check", "depends_on": ["n1"]}]
    run_id = crud.create_run("Tesla revenue report")
    rec = RunRecorder(run_id)
    for nid, skill, agent, out in (("n1", "drafting", "drafting-v1", DRAFT), ("n2", "chart", "chart-local", chart),
                                   ("n3", "fact_check", "fact_check-v1", fc)):
        await rec("agent_routed", {"node_id": nid, "reason": f"{agent} won on trust"})
        await rec("node_finished", {"node_id": nid, "skill": skill, "agent": agent, "output": out, "quality": 1.0,
                                    "duration_s": 2.0, "usage": {"tokens_in": 100, "tokens_out": 50}})
    await rec("run_finished", {"status": "complete", "usage": {"total": {"llm_calls": 3, "cost_usd": 0.0001}}})
    conflict = {"id": "c1", "status": "resolved", "explanation": "Tesla revenue: 96.77 vs 97.69",
                "resolution": {"value": "$96.77 billion"}}
    crud.finish_run(run_id, plan, "complete", [conflict], time.time())
    return run_id


async def test_report_contains_text_chart_sources_factcheck_and_provenance():
    run_id = await _run()
    c = builder.collect(crud.get_run(run_id))
    assert c["sources"] == [(1, "SEC EDGAR 10-K data: Tesla", "https://data.sec.gov/x.json")]
    assert len(c["charts"]) == 1 and c["facts"][0]["verdict"] == "supported"

    doc = Document(io.BytesIO(builder.to_docx(c)))
    text = "\n".join(p.text for p in doc.paragraphs)
    cells = " ".join(cell.text for t in doc.tables for row in t.rows for cell in row.cells)
    assert "Tesla revenue report" in text and "$96.77 billion" in text
    assert "[1] SEC EDGAR 10-K data: Tesla" in text and "Decision: $96.77 billion" in text
    assert "supported" in cells and "chart-local" in cells and "(local)" in cells
    assert len(doc.inline_shapes) == 1                                      # the chart image

    page = builder.to_html(c)
    assert '<sup><a href="https://data.sec.gov/x.json">1</a></sup>' in page   # clickable citation
    assert "data:image/png;base64," in page and "Save as PDF" in page and "<table>" in page


def test_report_endpoints():
    import asyncio
    import main
    run_id = asyncio.run(_run())
    client = TestClient(main.app)
    docx = client.get(f"/runs/{run_id}/report.docx")
    assert docx.status_code == 200 and docx.content[:2] == b"PK"
    assert "attachment" in docx.headers["content-disposition"]
    html = client.get(f"/runs/{run_id}/report.html")
    assert html.status_code == 200 and "How this report was produced" in html.text
    assert client.get("/runs/nope/report.docx").status_code == 404
