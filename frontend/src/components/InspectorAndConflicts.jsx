import NodeOutput from "./NodeOutput";
import { useState, useRef } from "react";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";

const BACKEND_URL = "http://127.0.0.1:8000";

export default function InspectorAndConflicts({
  plan = [],
  result = {},
  conflicts = [],
  selectedNode,
  onSelectNode,
  runId = null,
  onReviewed = null,
  nodeStatus = {},
  usage = null,
}) {
  const [copied, setCopied] = useState(false);
  const [rerun, setRerun] = useState({});
  const [busy, setBusy] = useState(null);
  const [reviewError, setReviewError] = useState(null);
  const [forks, setForks] = useState({});
  const conflictSectionRef = useRef(null);

  // Find the selected node object
  const activeNode = plan.find((n) => n.id === selectedNode) || plan[0];
  const activeOutput = activeNode ? result[activeNode.id] || "No output produced for this node." : "";

  // Check if active node is conflicted
  const nodeConflicts = conflicts.filter((c) =>
    (c.between || []).includes(activeNode?.id)
  );

  // Copy handler
  const handleCopy = () => {
    if (!activeOutput) return;
    navigator.clipboard.writeText(activeOutput);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Export Council Report as Markdown
  const handleExportReport = () => {
    let md = `# AGORA Council Synthesis Report\nGenerated: ${new Date().toLocaleString()}\n\n`;
    md += `## 1. DAG Topology Execution Plan\n`;
    plan.forEach((n) => {
      const deps = (n.depends_on || []).length > 0 ? n.depends_on.map((d) => `[${d}]`).join(", ") : "None (Root)";
      md += `- **Node [${n.id}]** (${n.agent}) — Dependencies: ${deps}\n`;
    });
    md += `\n## 2. Verified Agent Outputs\n\n`;
    plan.forEach((n) => {
      md += `### Node [${n.id}] — Agent: ${n.agent}\n`;
      md += `${result[n.id] || "No output recorded"}\n\n`;
    });
    if (conflicts.length > 0) {
      md += `## 3. Factual Conflict Arbitration Chamber\n\n`;
      conflicts.forEach((c, i) => {
        md += `### Case #${i + 1}: Disagreement between [${c.between?.join("] and [")}]\n`;
        md += `- **Factual Divergence:** ${c.explanation}\n`;
        md += `- **Suggested Resolution:** ${c.suggested_resolution}\n\n`;
      });
    } else {
      md += `## 3. Factual Consistency Status\nUnanimous consensus confirmed across all agent nodes with 0 factual divergences.\n`;
    }
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `agora-council-report-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Human approval gate: send the reviewer's decision to the backend
  const resolveConflict = async (conflict, choice) => {
    if (!runId) return;
    setBusy(conflict.id);
    setReviewError(null);
    try {
      const res = await axios.post(
        `${BACKEND_URL}/runs/${runId}/conflicts/${conflict.id}/resolve`,
        { choice, rerun: !!rerun[conflict.id] },
        { timeout: 240000 }
      );
      if (res.data.fork) setForks((prev) => ({ ...prev, [conflict.id]: res.data.fork }));
      if (onReviewed) onReviewed(res.data.conflicts, res.data.run_status);
    } catch (e) {
      setReviewError(e.response?.data?.detail || e.message);
    } finally {
      setBusy(null);
    }
  };

  // Stepper handlers
  const currentIndex = plan.findIndex((n) => n.id === activeNode?.id);
  const prevNode = currentIndex > 0 ? plan[currentIndex - 1] : null;
  const nextNode = currentIndex < plan.length - 1 ? plan[currentIndex + 1] : null;

  const scrollToConflicts = () => {
    conflictSectionRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className="inspector-and-conflicts">
      {/* Node Output Inspector */}
      {activeNode && (
        <section className="inspector-section">
          <div className="inspector-header">
            <div className="inspector-title-area">
              <span className="inspector-badge">Agent Output Inspector</span>
              <h3 className="inspector-node-title">
                Node [{activeNode.id}] • <span className="inspector-agent-name">{activeNode.agent}</span>
              </h3>
            </div>

            <div className="inspector-controls">
              <div className="inspector-stepper">
                <button
                  className="btn-step"
                  onClick={() => prevNode && onSelectNode(prevNode.id)}
                  disabled={!prevNode}
                  title={prevNode ? `Previous: [${prevNode.id}]` : "No previous node"}
                >
                  ← Prev
                </button>
                <span className="step-counter">
                  {currentIndex + 1} / {plan.length}
                </span>
                <button
                  className="btn-step"
                  onClick={() => nextNode && onSelectNode(nextNode.id)}
                  disabled={!nextNode}
                  title={nextNode ? `Next: [${nextNode.id}]` : "No next node"}
                >
                  Next →
                </button>
              </div>

              <button className="btn-copy" onClick={handleCopy} title="Copy output text">
                {copied ? (
                  <>
                    <span className="copy-check">✓</span> Copied
                  </>
                ) : (
                  <>
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="9" y="9" width="13" height="13" rx="2" />
                      <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                    </svg>
                    Copy Output
                  </>
                )}
              </button>

              <button className="btn-export" onClick={handleExportReport} title="Export full plan & outputs as markdown">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" />
                </svg>
                Export Briefing (.md)
              </button>
              {runId && (
                <>
                  <a className="btn-export" href={`${BACKEND_URL}/runs/${runId}/report.docx`}
                     title="Cited report as a Word document: text, chart, sources, fact-check, conflicts, how it was produced">
                    📄 Word report
                  </a>
                  <a className="btn-export" href={`${BACKEND_URL}/runs/${runId}/report.html`} target="_blank" rel="noreferrer"
                     title="Printable report: use Save as PDF">
                    🖨 Printable report (PDF)
                  </a>
                </>
              )}
            </div>
          </div>

          {/* Conflict warning banner on the active node */}
          {nodeConflicts.length > 0 && (
            <div className="node-conflict-alert">
              <div className="alert-content">
                <span className="alert-icon">⚡</span>
                <div>
                  <strong>Factual Disagreement Detected:</strong> Node [{activeNode.id}] has contradictory claims
                  flagged against{" "}
                  {nodeConflicts.map((c) =>
                    c.between
                      .filter((id) => id !== activeNode.id)
                      .map((id) => `[${id}]`)
                      .join(", ")
                  )}
                  .
                </div>
              </div>
              <button className="btn-jump-conflict" onClick={scrollToConflicts}>
                Review Arbitration Finding ↓
              </button>
            </div>
          )}

          {/* Node Metadata Strip */}
          <div className="node-meta-strip">
            <div className="meta-item">
              <span className="meta-k">Role:</span>
              <span className="meta-v">{activeNode.agent}</span>
            </div>
            <div className="meta-item">
              <span className="meta-k">Lineage:</span>
              <span className="meta-v">
                {(activeNode.depends_on || []).length === 0
                  ? "Independent Root Node"
                  : `Antecedents: ${(activeNode.depends_on || []).map((d) => `[${d}]`).join(", ")}`}
              </span>
            </div>
            <div className="meta-item">
              <span className="meta-k">Agent:</span>
              <span className="meta-v">
                {nodeStatus[activeNode.id]?.agent || "—"}
                {nodeStatus[activeNode.id]?.quality != null && ` · quality ${nodeStatus[activeNode.id].quality}`}
              </span>
            </div>
            {nodeStatus[activeNode.id]?.usage && (
              <div className="meta-item">
                <span className="meta-k">Cost:</span>
                <span className="meta-v">
                  {nodeStatus[activeNode.id].usage.llm_calls} LLM calls ·{" "}
                  {(nodeStatus[activeNode.id].usage.tokens_in + nodeStatus[activeNode.id].usage.tokens_out).toLocaleString()}{" "}
                  tokens · ${nodeStatus[activeNode.id].usage.cost_usd.toFixed(4)} notional
                  {usage && ` (run total $${usage.total.cost_usd.toFixed(4)})`}
                </span>
              </div>
            )}
            {nodeStatus[activeNode.id]?.revision && (
              <div className="meta-item">
                <span className="meta-k">Self-corrected:</span>
                <span className="meta-v">
                  {Math.round(nodeStatus[activeNode.id].revision.supported_rate_before * 100)}% →{" "}
                  {Math.round(nodeStatus[activeNode.id].revision.supported_rate_after * 100)}% of claims supported after{" "}
                  {nodeStatus[activeNode.id].revision.rounds} fact-check round(s)
                </span>
              </div>
            )}
            <div className="meta-item">
              <span className="meta-k">Output Volume:</span>
              <span className="meta-v">
                {activeOutput.split(/\s+/).filter(Boolean).length} words ({activeOutput.length} chars)
              </span>
            </div>
          </div>

          {/* Output Content */}
          <AnimatePresence mode="wait">
            <motion.div
              key={activeNode.id}
              className="output-display-box"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              <div className="output-prose"><NodeOutput text={activeOutput} /></div>
              {nodeStatus[activeNode.id]?.revision && (
                <details style={{ marginTop: 12, opacity: 0.85 }}>
                  <summary style={{ cursor: "pointer", color: "#f5ab3d" }}>
                    Show the original version (before fact-check feedback)
                  </summary>
                  <div className="output-prose"><NodeOutput text={nodeStatus[activeNode.id].revision.original_output} /></div>
                </details>
              )}
            </motion.div>
          </AnimatePresence>
        </section>
      )}

      {/* Conflicts Section */}
      <section className="conflicts-section" ref={conflictSectionRef}>
        <div className="conflicts-section-header">
          <div>
            <span className="section-eyebrow">Arbitration Chamber</span>
            <h3 className="section-title">Factual Consistency & Dispute Arbitration</h3>
          </div>
          <div className="conflicts-summary-badge">
            {conflicts.length > 0 ? (
              <span className="conflict-badge-active">
                ⚡ {conflicts.length} {conflicts.length === 1 ? "Disagreement" : "Disagreements"} Intercepted
              </span>
            ) : (
              <span className="conflict-badge-clean">✓ Unanimous Consensus</span>
            )}
          </div>
        </div>

        {conflicts.length === 0 ? (
          <div className="consensus-card">
            <div className="consensus-body">
              <h4 className="consensus-title">No conflicting figures found</h4>
              <p className="consensus-text">
                Every numeric claim was extracted as (entity, metric, period, value) and compared across nodes with
                unit and rounding tolerance. No two nodes state different values for the same fact. Fact-check
                verdicts are not treated as competing claims.
              </p>
            </div>
          </div>
        ) : (
          <div className="conflicts-list">
            {reviewError && <div style={{ color: "#ff9187", marginBottom: 12 }}>Review failed: {reviewError}</div>}
            {conflicts.map((conflict, idx) => {
              const resolved = conflict.status === "resolved";
              const auto = conflict.status === "auto_resolved";
              const sides = conflict.sides || [];
              const fork = forks[conflict.id];
              return (
                <motion.div
                  key={conflict.id || idx}
                  className={`conflict-card ${resolved ? "conflict-ratified" : ""}`}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: idx * 0.1 }}
                >
                  <div className="conflict-header">
                    <div className="conflict-parties">
                      <span className="party-chip">{conflict.label || "Disputed fact"}</span>
                      <span className="party-vs">nodes {(conflict.between || []).map((n) => `[${n}]`).join(" ")}</span>
                    </div>
                    <div className="arbitration-status-tag">
                      {resolved ? (
                        <span className="tag-ratified">✓ Resolved by reviewer: {conflict.resolution?.value}</span>
                      ) : auto ? (
                        <span className="tag-ratified">⚙ Auto-resolved (low-stakes): {conflict.resolution?.value} · you can override</span>
                      ) : (
                        <span>Awaiting human review · policy: {conflict.policy}</span>
                      )}
                    </div>
                  </div>

                  <div className="disputed-claims-grid">
                    {sides.map((side, i) => (
                      <div className="claim-box" key={i}
                           style={i === conflict.recommended ? { borderColor: "rgba(121,212,139,0.6)" } : undefined}>
                        <div className="claim-header">
                          <span className="claim-author">
                            {side.value} {i === conflict.recommended && <span style={{ color: "#79d48b" }}>· recommended</span>}
                          </span>
                        </div>
                        <div style={{ fontSize: 12, opacity: 0.85, margin: "4px 0 8px" }}>
                          Nodes {side.nodes.map((n) => `[${n}]`).join(" ")} · {side.agents.join(", ")}
                          <br />
                          Source: {side.authority_reason} (authority {side.authority}) · agent trust {side.trust}
                        </div>
                        {side.claims.slice(0, 3).map((c, j) => (
                          <div className="claim-text" key={j} style={{ marginBottom: 6 }}>
                            [{c.node_id}] "{c.quote}"
                            {c.sources.map((s) => (
                              <a key={s.url} href={s.url} target="_blank" rel="noreferrer"
                                 style={{ marginLeft: 6, fontStyle: "normal", color: "#f5ab3d" }}>[{s.id}]</a>
                            ))}
                          </div>
                        ))}
                        {!resolved && (
                          <button className="btn-ratify" disabled={!runId || busy === conflict.id}
                                  onClick={() => resolveConflict(conflict, i)}>
                            {busy === conflict.id ? "Saving decision…"
                              : auto ? (i === conflict.recommended ? `Confirm ${side.value}` : `Override: accept ${side.value}`)
                              : `Accept ${side.value}`}
                          </button>
                        )}
                      </div>
                    ))}
                  </div>

                  <div className="discrepancy-box">
                    <div className="box-label"><span className="label-icon">🔍</span><span>What disagrees:</span></div>
                    <p className="explanation-text">{conflict.explanation}</p>
                  </div>

                  <div className="resolution-box">
                    <div className="box-label"><span className="label-icon">⚖️</span><span>Recommendation:</span></div>
                    <p className="resolution-text">{conflict.suggested_resolution}</p>
                  </div>

                  <div className="conflict-ratify-bar">
                    {!resolved && !auto && (
                      <button className="btn-ratify" style={{ marginRight: 12 }} disabled={!runId || busy === conflict.id}
                              onClick={() => resolveConflict(conflict, conflict.recommended ?? 0)}
                              title="Apply the recommended side now; or choose a side above (Let me decide)">
                        ⚡ Auto-apply recommendation
                      </button>
                    )}
                    {!resolved ? (
                      <label className="ratify-caption" style={{ cursor: "pointer" }}>
                        <input type="checkbox" checked={!!rerun[conflict.id]}
                               onChange={(e) => setRerun((p) => ({ ...p, [conflict.id]: e.target.checked }))} />{" "}
                        Also re-run the losing node with the approved figure (fork from checkpoint; downstream nodes
                        re-run too). Your decision is stored and updates both agents' reputation.
                      </label>
                    ) : (
                      <span className="ratify-caption">
                        Decision stored in the run's event log; winning agent +1 graded outcome, losing agent(s) 0
                        (counted twice).
                        {fork && ` Corrected fork run ${fork.run_id.slice(0, 8)}: re-ran ${fork.rerun_nodes.join(", ")}, status ${fork.status}.`}
                      </span>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
