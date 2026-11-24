import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { VegaChart } from "./NodeOutput";

// Palette (validated with the dataviz validator on the panel surface #241c14, dark mode):
// series v1 / v2 = categorical slots 1-2; run status = the reserved status palette (always with a label).
const SERIES = { v1: "#3987e5", v2: "#d95926" };
const STATUS = { complete: "#0ca30c", needs_review: "#fab219", partial: "#ec835a", failed: "#d03b3b",
                 running: "#8a8278", planned: "#8a8278" };
const STATUS_LABEL = { complete: "✓ complete", needs_review: "⚖ needs review", partial: "◐ partial",
                       failed: "✕ failed", running: "running", planned: "planned" };
const TEXT = "#f1e8da";
const MUTED = "rgba(241,232,218,0.65)";
const PANEL = "#241c14";
const LINE = "rgba(245,171,61,0.25)";
const card = { background: PANEL, border: `1px solid ${LINE}`, borderRadius: 12, padding: 16, marginBottom: 16, color: TEXT };
const AXIS = { gridColor: "rgba(241,232,218,0.08)", domainColor: "rgba(241,232,218,0.25)", tickColor: "rgba(241,232,218,0.25)",
               labelColor: MUTED, titleColor: MUTED };

const pct = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const num = (v, d = 2) => (v == null ? "—" : Number(v).toFixed(d));

function Tile({ label, value, note }) {
  return (
    <div style={{ ...card, marginBottom: 0, padding: 14 }}>
      <div style={{ fontSize: 12, color: MUTED }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, margin: "4px 0" }}>{value}</div>
      {note && <div style={{ fontSize: 12, color: MUTED }}>{note}</div>}
    </div>
  );
}

function Meter({ value }) {
  if (value == null) return <span style={{ color: MUTED }}>—</span>;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 70, height: 8, background: "rgba(241,232,218,0.12)", borderRadius: 4, overflow: "hidden" }}>
        <span style={{ display: "block", width: `${value * 100}%`, height: "100%", background: SERIES.v1, borderRadius: 4 }} />
      </span>
      {pct(value)}
    </span>
  );
}

function runsSpec(perDay) {
  const statuses = Object.keys(STATUS).filter((s) => perDay.some((d) => d[s]));
  const values = perDay.flatMap((d) => statuses.filter((s) => d[s]).map((s) => ({ day: d.day, status: STATUS_LABEL[s], runs: d[s] })));
  return {
    $schema: "https://vega.github.io/schema/vega-lite/v5.json",
    width: "container", height: 200, data: { values },
    mark: { type: "bar", cornerRadiusEnd: 4, stroke: PANEL, strokeWidth: 2 },
    encoding: {
      x: { field: "day", type: "ordinal", title: null, axis: { labelAngle: 0 } },
      y: { field: "runs", type: "quantitative", title: "Runs", stack: "zero", axis: { tickMinStep: 1 } },
      color: { field: "status", type: "nominal", title: "Status",
               scale: { domain: statuses.map((s) => STATUS_LABEL[s]), range: statuses.map((s) => STATUS[s]) } },
      tooltip: [{ field: "day", title: "Day" }, { field: "status", title: "Status" }, { field: "runs", title: "Runs" }],
    },
    config: { axis: AXIS, legend: { labelColor: TEXT, titleColor: MUTED } },
  };
}

function trustSpec(skill, series) {
  const values = Object.entries(series)
    .filter(([agent]) => agent.startsWith(`${skill}-`))
    .flatMap(([agent, pts]) => pts.map((p) => ({ agent, t: p.t, trust: p.trust, quality: p.quality, source: p.source })));
  const agents = [`${skill}-v1`, `${skill}-v2`];
  return {
    values: values.length,
    spec: {
      $schema: "https://vega.github.io/schema/vega-lite/v5.json",
      width: "container", height: 140, data: { values },
      mark: { type: "line", strokeWidth: 2, point: { size: 64, filled: true, stroke: PANEL, strokeWidth: 2 } },
      encoding: {
        x: { field: "t", type: "temporal", title: null },
        y: { field: "trust", type: "quantitative", title: "Trust", scale: { domain: [0, 1] } },
        color: { field: "agent", type: "nominal", title: null, scale: { domain: agents, range: [SERIES.v1, SERIES.v2] } },
        tooltip: [{ field: "agent", title: "Agent" }, { field: "t", type: "temporal", title: "When", format: "%d %b %H:%M" },
                  { field: "trust", title: "Trust after", format: ".3f" }, { field: "quality", title: "Graded quality" },
                  { field: "source", title: "Evidence" }],
      },
      config: { axis: AXIS, legend: { orient: "top", labelColor: TEXT } },
    },
  };
}

export default function Dashboard({ backendUrl }) {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${backendUrl}/metrics/overview`, { params: { days }, timeout: 15000 });
      setData(res.data);
      setError(null);
    } catch (e) {
      setError(`Could not load metrics: ${e.response?.data?.detail || e.message}`);
    } finally {
      setLoading(false);
    }
  }, [backendUrl, days]);

  useEffect(() => { load(); }, [load]);

  const r = data?.runs;
  const c = data?.conflicts;
  const skills = ["research", "drafting", "chart", "fact_check"];

  return (
    <div style={{ color: TEXT }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 14 }}>
        <h3 style={{ margin: 0, flex: 1 }}>Observability</h3>
        <label style={{ fontSize: 13, color: MUTED }}>
          Window{" "}
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}
                  style={{ background: "#0e0c0a", color: TEXT, border: `1px solid ${LINE}`, borderRadius: 8, padding: "6px 8px" }}>
            <option value={1}>last 24 h</option>
            <option value={7}>last 7 days</option>
            <option value={30}>last 30 days</option>
            <option value={365}>last year</option>
          </select>
        </label>
        <button onClick={load} disabled={loading}
                style={{ background: "transparent", color: "#f5ab3d", border: `1px solid ${LINE}`, borderRadius: 8, padding: "6px 12px", cursor: "pointer" }}>
          {loading ? "Loading…" : "↻ Refresh"}
        </button>
      </div>
      {error && <div style={{ ...card, color: "#ff9187" }}>{error}</div>}
      {data && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, marginBottom: 16 }}>
            <Tile label="Runs" value={r.total} note={`${r.forks} forks`} />
            <Tile label="Run success rate" value={pct(r.success_rate)} note="complete ÷ finished" />
            <Tile label="Avg run duration" value={r.avg_duration_s == null ? "—" : `${num(r.avg_duration_s, 1)} s`} />
            <Tile label="Notional LLM cost" value={`$${num(r.cost_usd, 4)}`} note={`${r.runs_with_cost} runs measured · free tiers = $0`} />
            <Tile label="Runs with a conflict" value={pct(c.conflict_rate)} note={`${c.total} structured · ${c.open} open`} />
            <Tile label="Human decisions" value={data.humans.conflict_decisions + data.humans.nodes_written_by_people}
                  note={`${data.humans.conflict_decisions} reviews · ${data.humans.nodes_written_by_people} nodes written`} />
            <Tile label="Audit log" value={data.audit.ok ? "✓ intact" : "✕ broken"}
                  note={data.audit.ok ? `${data.audit.entries} entries, hash chain verified` : `chain breaks at entry ${data.audit.broken_at}`} />
          </div>

          <div style={card}>
            <b>Runs per day, by status</b>
            {r.per_day.length ? <VegaChart source={JSON.stringify(runsSpec(r.per_day))} /> : <div style={{ color: MUTED }}>No runs in this window.</div>}
          </div>

          <div style={card}>
            <b>Agents</b>
            <span style={{ fontSize: 12, color: MUTED }}> · from node events in this window; trust is the current Beta posterior</span>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, marginTop: 8 }}>
                <thead>
                  <tr style={{ color: MUTED, textAlign: "left" }}>
                    {["Agent", "Model", "Trust (95% CI)", "Nodes", "Success", "Avg quality", "Avg latency", "Retries (infra / quality)", "Cost / node"].map((h) => (
                      <th key={h} style={{ padding: "6px 8px", borderBottom: `1px solid ${LINE}`, fontWeight: 500 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.agents.map((a) => (
                    <tr key={a.agent}>
                      <td style={{ padding: "6px 8px" }}>
                        <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 4, marginRight: 6,
                                       background: a.agent.endsWith("-v1") ? SERIES.v1 : SERIES.v2 }} />
                        {a.agent}
                      </td>
                      <td style={{ padding: "6px 8px", color: MUTED }}>{a.model}</td>
                      <td style={{ padding: "6px 8px" }}>{num(a.trust_mean, 3)} <span style={{ color: MUTED }}>({a.trust_ci95 ? `${num(a.trust_ci95[0])}–${num(a.trust_ci95[1])}` : "—"})</span></td>
                      <td style={{ padding: "6px 8px" }}>{a.nodes}</td>
                      <td style={{ padding: "6px 8px" }}><Meter value={a.success_rate} /></td>
                      <td style={{ padding: "6px 8px" }}>{num(a.avg_quality)}</td>
                      <td style={{ padding: "6px 8px" }}>{a.avg_duration_s == null ? "—" : `${num(a.avg_duration_s, 1)} s`}</td>
                      <td style={{ padding: "6px 8px" }}>{a.infra_failures} / {a.quality_failures}</td>
                      <td style={{ padding: "6px 8px" }}>{a.cost_per_node_usd == null ? "—" : `$${num(a.cost_per_node_usd, 4)}`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div style={card}>
            <b>Trust over time</b>
            <span style={{ fontSize: 12, color: MUTED }}> · every graded outcome (output checks, fact-check feedback, reviewed conflicts)</span>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 12, marginTop: 8 }}>
              {skills.map((skill) => {
                const { values, spec } = trustSpec(skill, data.reputation);
                return (
                  <div key={skill} style={{ border: `1px solid ${LINE}`, borderRadius: 8, padding: 8 }}>
                    <div style={{ fontSize: 13 }}>{skill}</div>
                    {values ? <VegaChart source={JSON.stringify(spec)} /> : <div style={{ color: MUTED, fontSize: 12, padding: 20 }}>No graded outcomes in this window.</div>}
                  </div>
                );
              })}
            </div>
          </div>

          <div style={card}>
            <b>Conflicts</b>
            <div style={{ fontSize: 13, marginTop: 6, lineHeight: 1.7 }}>
              {c.total} structured conflicts: {c.resolved} resolved by a reviewer ({c.reviewer_agreed_with_recommendation} agreed with the
              recommendation), {c.open} open. Policies used:{" "}
              {Object.entries(c.by_policy).map(([p, n]) => `${p} ×${n}`).join(", ") || "—"}.
              {c.legacy_pairwise > 0 && <span style={{ color: MUTED }}> ({c.legacy_pairwise} older pairwise-format conflicts not counted.)</span>}
            </div>
          </div>
          <div style={{ fontSize: 12, color: MUTED }}>Generated {new Date(data.generated_at).toLocaleString()} · costs are {data.pricing}</div>
        </>
      )}
    </div>
  );
}
