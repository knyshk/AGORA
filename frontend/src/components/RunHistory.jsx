import { useEffect, useState } from "react";
import axios from "axios";
import NodeOutput from "./NodeOutput";

const GOLD = "#f5ab3d";
const PANEL = "#241c14";
const LINE = "rgba(245,171,61,0.25)";
const COLORS = { done: "#79d48b", running: GOLD, failed: "#ff9187", skipped: "#8a8278", pending: "#8a8278" };

const card = { background: PANEL, border: `1px solid ${LINE}`, borderRadius: 12, padding: 16, marginBottom: 16, color: "#f1e8da" };
const button = { background: GOLD, color: "#0e0c0a", border: "none", borderRadius: 8, padding: "8px 14px", fontWeight: 600, cursor: "pointer" };
const input = { background: "#0e0c0a", color: "#f1e8da", border: `1px solid ${LINE}`, borderRadius: 8, padding: "8px 10px" };

function replayState(events, upto) {
  const status = {};
  const outputs = {};
  const reused = {};
  const usage = {};
  let runUsage = null;
  for (const e of events) {
    if (e.seq > upto) break;
    const p = e.payload;
    if (e.type === "node_started") status[p.node_id] = "running";
    if (e.type === "node_finished") {
      status[p.node_id] = "done";
      outputs[p.node_id] = p.output;
      reused[p.node_id] = !!p.reused;
      if (p.usage) usage[p.node_id] = p.usage;
    }
    if (e.type === "node_failed") {
      status[p.node_id] = "failed";
      if (p.usage) usage[p.node_id] = p.usage;
    }
    if (e.type === "node_skipped") status[p.node_id] = "skipped";
    if (e.type === "run_finished" && p.usage) runUsage = p.usage;
  }
  return { status, outputs, reused, usage, runUsage };
}

export default function RunHistory({ backendUrl }) {
  const [runs, setRuns] = useState([]);
  const [detail, setDetail] = useState(null);
  const [upto, setUpto] = useState(0);
  const [agents, setAgents] = useState([]);
  const [forkNode, setForkNode] = useState("");
  const [forkAgent, setForkAgent] = useState("");
  const [forkInstruction, setForkInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const loadRuns = async () => {
    try {
      const res = await axios.get(`${backendUrl}/runs`, { timeout: 10000 });
      setRuns(res.data);
    } catch (e) {
      setError("Could not load runs: " + (e.message || e));
    }
  };

  const loadDetail = async (id) => {
    try {
      const res = await axios.get(`${backendUrl}/runs/${id}`, { timeout: 10000 });
      setDetail(res.data);
      const events = res.data.events;
      setUpto(events.length ? events[events.length - 1].seq : 0);
      const plan = res.data.run.plan || [];
      setForkNode(plan.length ? plan[0].id : "");
      setForkAgent("");
    } catch (e) {
      setError("Could not load run: " + (e.message || e));
    }
  };

  useEffect(() => {
    loadRuns();
    axios.get(`${backendUrl}/reputation/scores`).then((r) => setAgents(Object.values(r.data))).catch(() => {});
  }, [backendUrl]);

  const doFork = async () => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const body = { rerun_node: forkNode };
      if (forkAgent) body.agent = forkAgent;
      if (forkInstruction.trim()) body.instruction = forkInstruction.trim();
      const res = await axios.post(`${backendUrl}/runs/${detail.run.id}/fork`, body, { timeout: 180000 });
      setMessage(`Fork complete. Reused: ${res.data.reused_nodes.join(", ") || "none"}. Re-ran: ${res.data.rerun_nodes.join(", ")}.`);
      await loadRuns();
      await loadDetail(res.data.run_id);
    } catch (e) {
      setError("Fork failed: " + (e.response?.data?.detail || e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const events = detail?.events || [];
  const maxSeq = events.length ? events[events.length - 1].seq : 0;
  const state = detail ? replayState(events, upto) : null;
  const plan = detail?.run.plan || [];
  const currentEvent = events.find((e) => e.seq === upto);
  const parent = detail && runs.find((r) => r.id === detail.run.parent_run_id);
  const agentOptions = agents.filter((a) => plan.find((n) => n.id === forkNode)?.agent === a.skill);

  return (
    <div style={{ marginTop: 24 }}>
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ color: GOLD, letterSpacing: 2, fontSize: 12 }}>RUN HISTORY</div>
            <h2 style={{ margin: "4px 0 0" }}>Saved runs, replay and fork</h2>
          </div>
          <button style={button} onClick={loadRuns}>Refresh</button>
        </div>
        {error && <div style={{ color: "#ff9187", marginTop: 10 }}>{error}</div>}
        {message && <div style={{ color: "#79d48b", marginTop: 10 }}>{message}</div>}
        <div style={{ marginTop: 12, maxHeight: 220, overflowY: "auto" }}>
          {runs.length === 0 && <div style={{ opacity: 0.7 }}>No runs yet. Run a task first.</div>}
          {runs.map((r) => (
            <div key={r.id} onClick={() => loadDetail(r.id)}
              style={{ padding: "8px 10px", borderRadius: 8, cursor: "pointer", marginBottom: 4,
                       border: `1px solid ${detail?.run.id === r.id ? GOLD : LINE}` }}>
              <span style={{ color: COLORS[r.status === "complete" ? "done" : r.status] || GOLD, fontWeight: 600 }}>{r.status}</span>
              {" · "}{r.query.slice(0, 70)}
              <span style={{ opacity: 0.6 }}> · {r.duration_s ?? "?"}s · {r.conflict_count} conflicts</span>
              {r.parent_run_id && <span style={{ color: GOLD }}> · fork</span>}
            </div>
          ))}
        </div>
      </div>

      {detail && (
        <>
          <div style={card}>
            <div style={{ color: GOLD, letterSpacing: 2, fontSize: 12 }}>TIMELINE REPLAY</div>
            <div style={{ margin: "8px 0" }}>
              Event {upto} / {maxSeq}{currentEvent ? ` — ${currentEvent.type}` : ""}
            </div>
            <input type="range" min={0} max={maxSeq} value={upto}
                   onChange={(e) => setUpto(Number(e.target.value))} style={{ width: "100%" }} />
            <div style={{ marginTop: 14 }}>
              {plan.map((n) => {
                const st = state.status[n.id] || "pending";
                const out = state.outputs[n.id];
                return (
                  <div key={n.id} style={{ border: `1px solid ${LINE}`, borderLeft: `4px solid ${COLORS[st]}`,
                                           borderRadius: 8, padding: 10, marginBottom: 8 }}>
                    <b>{n.id}</b> · {n.agent}
                    <span style={{ color: COLORS[st], marginLeft: 8 }}>{st}</span>
                    {state.reused[n.id] && <span style={{ color: GOLD, marginLeft: 8 }}>reused from parent</span>}
                    <span style={{ opacity: 0.6, marginLeft: 8 }}>depends on: {n.depends_on.join(", ") || "none"}</span>
                    {state.usage[n.id] && (
                      <span style={{ opacity: 0.75, marginLeft: 8, fontSize: 12 }}>
                        · {state.usage[n.id].llm_calls} LLM calls ·{" "}
                        {(state.usage[n.id].tokens_in + state.usage[n.id].tokens_out).toLocaleString()} tokens
                        {state.usage[n.id].tokens_estimated ? " (est.)" : ""} · ${state.usage[n.id].cost_usd.toFixed(4)}
                      </span>
                    )}
                    {out && (
                      <details style={{ marginTop: 6 }}>
                        <summary style={{ cursor: "pointer", color: GOLD }}>Show output ({out.length} chars)</summary>
                        <div style={{ maxHeight: 520, overflowY: "auto", fontSize: 13 }}><NodeOutput text={out} /></div>
                      </details>
                    )}
                  </div>
                );
              })}
            </div>
            {state.runUsage && (
              <div style={{ fontSize: 13, opacity: 0.85, margin: "6px 0" }}>
                Run total: {state.runUsage.total.llm_calls} LLM calls ·{" "}
                {(state.runUsage.total.tokens_in + state.runUsage.total.tokens_out).toLocaleString()} tokens · $
                {state.runUsage.total.cost_usd.toFixed(4)} notional cost (free tiers actually charge $0)
                {state.runUsage.budget?.limit_usd != null &&
                  ` · budget $${state.runUsage.budget.limit_usd}, mode ${state.runUsage.budget.mode}`}
              </div>
            )}
            {detail.run.conflicts?.length > 0 && (
              <div style={{ color: "#ff9187" }}>Conflicts in this run: {detail.run.conflicts.length}</div>
            )}
            {parent && (
              <div style={{ opacity: 0.8, marginTop: 6 }}>
                Forked from {parent.id.slice(0, 8)} · parent took {parent.duration_s}s, this fork took {detail.run.duration_s}s
              </div>
            )}
          </div>

          <div style={card}>
            <div style={{ color: GOLD, letterSpacing: 2, fontSize: 12 }}>FORK FROM CHECKPOINT</div>
            <p style={{ opacity: 0.8 }}>
              Re-run one node (and only the nodes that depend on it). Everything else is reused from this run.
            </p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <select style={input} value={forkNode} onChange={(e) => { setForkNode(e.target.value); setForkAgent(""); }}>
                {plan.map((n) => <option key={n.id} value={n.id}>{n.id} ({n.agent})</option>)}
              </select>
              <select style={input} value={forkAgent} onChange={(e) => setForkAgent(e.target.value)}>
                <option value="">best agent (auto)</option>
                {agentOptions.map((a) => <option key={a.name} value={a.name}>{a.name} · {a.model}</option>)}
              </select>
              <input style={{ ...input, flex: 1, minWidth: 220 }} placeholder="Optional extra instruction for this node"
                     value={forkInstruction} onChange={(e) => setForkInstruction(e.target.value)} />
              <button style={{ ...button, opacity: busy ? 0.6 : 1 }} disabled={busy} onClick={doFork}>
                {busy ? "Forking..." : "Fork run"}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}