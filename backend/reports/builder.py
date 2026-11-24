"""Turn a stored run into a shareable, cited report (Word .docx, or a printable HTML page -> PDF).

Everything comes from the run's stored data: the final (possibly self-corrected) outputs, the event
log (routing, grades, self-correction, usage) and the audit-log head. Nothing is regenerated.
"""
import base64
import html
import io
import json
import re
from datetime import datetime

import markdown as md
import vl_convert as vlc
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

from agents.drafting_tools import SOURCE_LINE
from registry.registry import REGISTRY
from security.audit import verify_chain

VERDICT_ICON = {"supported": "✅", "unsupported": "⚠️", "contradicted": "❌", "unverifiable": "❔"}


# ---------------- collect ----------------

def _first(nodes, skill):
    return next((n for n in nodes if n["skill"] == skill and n["status"] == "done" and n["output"]), None)


def split_sources(text: str):
    body, _, tail = (text or "").partition("\n---\n")
    sources = [(int(i), t.strip(), u) for i, t, u in SOURCE_LINE.findall(tail)]
    note = "\n".join(l for l in tail.splitlines() if l.startswith("Citation check"))
    return body.strip(), sources, note


def chart_specs(text: str) -> list:
    specs = []
    for block in re.findall(r"```vega-lite\s*(.*?)```", text or "", flags=re.S):
        try:
            spec = json.loads(block)
        except ValueError:
            continue
        spec["width"] = 560
        spec.setdefault("config", {})["background"] = "white"
        specs.append(spec)
    return specs


def chart_png(spec: dict) -> bytes:
    return vlc.vegalite_to_png(spec, scale=2)


def fact_rows(text: str) -> list:
    rows = []
    for line in (text or "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[0].isdigit():
            verdict = next((v for v in ("unsupported", "contradicted", "unverifiable", "supported") if v in cells[2]), "?")
            rows.append({"claim": cells[1], "verdict": verdict, "evidence": cells[3]})
    return rows


def collect(data: dict) -> dict:
    run, nodes, events = data["run"], data["nodes"], data["events"]
    draft = _first(nodes, "drafting") or _first(nodes, "research")
    research = _first(nodes, "research")
    chart = _first(nodes, "chart")
    fc = _first(nodes, "fact_check")
    body, sources, note = split_sources(draft["output"] if draft else "")
    if research and not sources:
        _, sources, _ = split_sources(research["output"])
    finished = [e for e in events if e["type"] == "run_finished"]
    usage = (finished[-1]["payload"].get("usage") if finished else None) or {}
    node_info = {}
    for e in events:
        p = e["payload"]
        if e["type"] == "node_finished" and p.get("node_id"):
            node_info[p["node_id"]] = p
    routing = {e["payload"]["node_id"]: e["payload"].get("reason", "") for e in events
               if e["type"] == "agent_routed" and e["payload"].get("node_id")}
    corrections = [e["payload"] for e in events if e["type"] == "self_correction_finished"]
    return {"run": run, "body": body, "sources": sources, "citation_note": note,
            "charts": chart_specs(chart["output"]) if chart else [],
            "facts": fact_rows(fc["output"]) if fc else [],
            "conflicts": run.get("conflicts") or [], "plan": run.get("plan") or [], "node_info": node_info,
            "routing": routing, "usage": usage, "corrections": corrections, "audit": verify_chain()}


def provenance_rows(c: dict) -> list:
    rows = []
    for n in c["plan"]:
        info = c["node_info"].get(n["id"], {})
        agent = info.get("agent") or "—"
        m = REGISTRY.get(agent)
        u = info.get("usage") or {}
        rows.append({"node": n["id"], "skill": n["agent"], "agent": agent,
                     "model": m.model + (" (local)" if m.provider == "ollama" else "") if m else
                     ("written by a person" if str(agent).startswith("human:") else "—"),
                     "quality": "—" if info.get("quality") is None else f"{info['quality']:.2f}",
                     "time": f"{info.get('duration_s', 0):.1f} s" if info.get("duration_s") is not None else "—",
                     "tokens": f"{u.get('tokens_in', 0) + u.get('tokens_out', 0):,}" if u else "—",
                     "why": c["routing"].get(n["id"], "")})
    return rows


# ---------------- Word ----------------

INLINE = re.compile(r"(\*\*[^*]+\*\*|\[\d+(?:,\s*\d+)*\])")


def _runs(paragraph, text, sources):
    links = {i: u for i, _, u in sources}
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**"):
            paragraph.add_run(part.strip("*")).bold = True
        elif part.startswith("[") and part[1:-1].replace(",", "").replace(" ", "").isdigit():
            r = paragraph.add_run(part)
            r.font.superscript = True
            r.font.color.rgb = RGBColor(0x1C, 0x5C, 0xAB)
            first = int(re.findall(r"\d+", part)[0])
            if first in links:
                r.font.underline = True
        else:
            paragraph.add_run(part)


def _markdown_to_docx(doc, text, sources):
    lines, i = text.splitlines(), 0
    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not re.match(r"^\|\s*:?-{2,}", lines[i].strip()):
                    block.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            table = doc.add_table(rows=len(block), cols=max(len(r) for r in block))
            table.style = "Light Grid Accent 1"
            for r, row in enumerate(block):
                for col, cell in enumerate(row):
                    _runs(table.cell(r, col).paragraphs[0], cell, sources)
            continue
        if line.startswith("#"):
            level = min(len(line) - len(line.lstrip("#")), 3)
            doc.add_heading(line.lstrip("# ").strip(), level=level + 1)
        elif re.match(r"^\s*[-*] ", line):
            _runs(doc.add_paragraph(style="List Bullet"), re.sub(r"^\s*[-*] ", "", line), sources)
        elif line.strip():
            _runs(doc.add_paragraph(), line.strip(), sources)
        i += 1


def to_docx(c: dict) -> bytes:
    run = c["run"]
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    title = doc.add_heading(run["query"], level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    meta = doc.add_paragraph()
    meta.add_run(f"Generated by AGORA · run {run['id'][:8]} · {run['created_at'][:16].replace('T', ' ')} UTC · "
                 f"status {run['status']}").italic = True

    doc.add_heading("Report", level=1)
    _markdown_to_docx(doc, c["body"] or "(no report text in this run)", c["sources"])

    for spec in c["charts"]:
        doc.add_heading(spec.get("title", "Chart") if isinstance(spec.get("title"), str) else "Chart", level=2)
        doc.add_picture(io.BytesIO(chart_png(spec)), width=Inches(6))
        doc.add_paragraph("Every value in this chart was checked against the numbers in the research.").italic = True

    if c["sources"]:
        doc.add_heading("Sources", level=1)
        for i, t, u in c["sources"]:
            doc.add_paragraph(f"[{i}] {t} — {u}")
        if c["citation_note"]:
            doc.add_paragraph(c["citation_note"]).italic = True

    if c["facts"]:
        doc.add_heading("Fact check", level=1)
        doc.add_paragraph("Each cited claim was re-checked against the source it cites.")
        table = doc.add_table(rows=1, cols=3)
        table.style = "Light Grid Accent 1"
        for cell, head in zip(table.rows[0].cells, ("Claim", "Verdict", "Evidence")):
            cell.text = head
        for f in c["facts"]:
            row = table.add_row().cells
            row[0].text, row[1].text, row[2].text = f["claim"], f"{VERDICT_ICON.get(f['verdict'], '')} {f['verdict']}", f["evidence"]

    if c["corrections"]:
        doc.add_heading("Self-correction", level=2)
        for p in c["corrections"]:
            doc.add_paragraph(f"Round {p['round']}: supported claims {p['supported_rate_before']} → "
                              f"{p['supported_rate_after']} ({'kept' if p['accepted'] else 'rejected'}).")

    if c["conflicts"]:
        doc.add_heading("Conflicts between agents", level=1)
        for k in c["conflicts"]:
            doc.add_paragraph(k.get("explanation", ""), style="List Bullet")
            res = k.get("resolution")
            doc.add_paragraph(f"Decision: {res['value']} (by a reviewer)" if res else
                              f"Open — recommended: {k.get('suggested_resolution', '')}")

    doc.add_heading("How this report was produced", level=1)
    rows = provenance_rows(c)
    table = doc.add_table(rows=1, cols=6)
    table.style = "Light Grid Accent 1"
    for cell, head in zip(table.rows[0].cells, ("Step", "Agent", "Model", "Quality", "Time", "Tokens")):
        cell.text = head
    for r in rows:
        cells = table.add_row().cells
        for cell, v in zip(cells, (f"{r['node']} ({r['skill']})", r["agent"], r["model"], r["quality"], r["time"], r["tokens"])):
            cell.text = v
    total = (c["usage"] or {}).get("total") or {}
    doc.add_paragraph(f"LLM calls: {total.get('llm_calls', '—')} · notional cost: "
                      f"${total.get('cost_usd', 0):.4f} (free tiers are actually $0) · audit log "
                      f"{'intact' if c['audit']['ok'] else 'BROKEN'} ({c['audit']['entries']} entries).")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------- printable HTML (Save as PDF from the browser) ----------------

def _cite_links(body_html: str, sources) -> str:
    links = {i: u for i, _, u in sources}

    def link(m):
        ids = [int(x) for x in re.findall(r"\d+", m.group(0))]
        return "<sup>" + ", ".join(f'<a href="{html.escape(links[i])}">{i}</a>' if i in links else str(i)
                                   for i in ids) + "</sup>"
    return re.sub(r"\[\d+(?:,\s*\d+)*\]", link, body_html)


def to_html(c: dict) -> str:
    run = c["run"]
    e = html.escape
    parts = [f"<h1>{e(run['query'])}</h1>",
             f"<p class='meta'>Generated by AGORA · run {run['id'][:8]} · {run['created_at'][:16].replace('T', ' ')} UTC · "
             f"status {e(run['status'])} · <button onclick='window.print()'>Save as PDF</button></p>",
             "<h2>Report</h2>", _cite_links(md.markdown(c["body"] or "", extensions=["tables"]), c["sources"])]
    for spec in c["charts"]:
        img = base64.b64encode(chart_png(spec)).decode()
        parts.append(f"<figure><img src='data:image/png;base64,{img}' alt='chart'/>"
                     "<figcaption>Every value was checked against the research.</figcaption></figure>")
    if c["sources"]:
        parts.append("<h2>Sources</h2><ol class='src'>" + "".join(
            f"<li value='{i}'>{e(t)} — <a href='{e(u)}'>{e(u)}</a></li>" for i, t, u in c["sources"]) + "</ol>")
    if c["facts"]:
        parts.append("<h2>Fact check</h2><table><tr><th>Claim</th><th>Verdict</th><th>Evidence</th></tr>" + "".join(
            f"<tr><td>{e(f['claim'])}</td><td>{VERDICT_ICON.get(f['verdict'], '')} {f['verdict']}</td><td>{e(f['evidence'])}</td></tr>"
            for f in c["facts"]) + "</table>")
    if c["conflicts"]:
        parts.append("<h2>Conflicts between agents</h2><ul>" + "".join(
            f"<li>{e(k.get('explanation', ''))}<br><b>{'Decision: ' + e(k['resolution']['value']) if k.get('resolution') else 'Open'}</b></li>"
            for k in c["conflicts"]) + "</ul>")
    rows = provenance_rows(c)
    total = (c["usage"] or {}).get("total") or {}
    parts.append("<h2>How this report was produced</h2><table><tr><th>Step</th><th>Agent</th><th>Model</th>"
                 "<th>Quality</th><th>Time</th><th>Tokens</th><th>Why this agent</th></tr>" + "".join(
                     f"<tr><td>{r['node']} ({r['skill']})</td><td>{e(r['agent'])}</td><td>{e(r['model'])}</td>"
                     f"<td>{r['quality']}</td><td>{r['time']}</td><td>{r['tokens']}</td><td class='why'>{e(r['why'])}</td></tr>"
                     for r in rows) + "</table>"
                 f"<p class='meta'>LLM calls: {total.get('llm_calls', '—')} · notional cost ${total.get('cost_usd', 0):.4f} "
                 f"(free tiers are actually $0) · audit log {'intact' if c['audit']['ok'] else 'BROKEN'} "
                 f"({c['audit']['entries']} entries) · generated {datetime.now().strftime('%d %b %Y %H:%M')}</p>")
    css = """body{font-family:Georgia,serif;max-width:820px;margin:40px auto;color:#1b1b1b;line-height:1.55;padding:0 20px}
h1{font-size:28px;margin-bottom:4px}h2{border-bottom:1px solid #ddd;padding-bottom:4px;margin-top:32px}
.meta{color:#666;font-size:13px}table{border-collapse:collapse;width:100%;font-size:13px;margin:10px 0}
td,th{border:1px solid #ddd;padding:6px;vertical-align:top;text-align:left}th{background:#f4f4f2}
sup a{color:#1c5cab;text-decoration:none}figure{margin:20px 0}figure img{max-width:100%}
figcaption{color:#666;font-size:12px}.src{font-size:13px}.why{font-size:11px;color:#555}
@media print{button{display:none}a{color:#1b1b1b}}"""
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{e(run['query'])}</title><style>{css}</style></head><body>{''.join(parts)}</body></html>"
