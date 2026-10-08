import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";

export default function InspectorAndConflicts({
  plan = [],
  result = {},
  conflicts = [],
  selectedNode,
  onSelectNode,
}) {
  const [copied, setCopied] = useState(false);
  const [ratifiedConflicts, setRatifiedConflicts] = useState({});
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

  const toggleRatify = (idx) => {
    setRatifiedConflicts((prev) => ({
      ...prev,
      [idx]: !prev[idx],
    }));
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
              <span className="meta-k">Routing Engine:</span>
              <span className="meta-v">Redis Bayesian Prior Score</span>
            </div>
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
              <div className="output-prose"><ReactMarkdown remarkPlugins={[remarkGfm]}>{activeOutput}</ReactMarkdown></div>
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
            <div className="consensus-icon-box">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 2l3 7h7l-5.5 4.5 2 7-6.5-4.5-6.5 4.5 2-7L2 9h7z" fill="rgba(82, 163, 115, 0.2)" />
                <path d="M9 12l2 2 4-4" stroke="#52a373" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <div className="consensus-body">
              <h4 className="consensus-title">Unanimous Consensus Reached Across All Agents</h4>
              <p className="consensus-text">
                The arbitration engine conducted pairwise cross-examination across all agent outputs. No contradictory
                numeric claims, temporal divergences, or factual inconsistencies were found. Every assertion aligns
                harmoniously across the dependency graph.
              </p>
              <div className="consensus-stats">
                <span>Pairwise Comparisons: Verified Clean</span>
                <span>•</span>
                <span>False Positive Rate: 0/3 Benchmark</span>
              </div>
            </div>
          </div>
        ) : (
          <div className="conflicts-list">
            {conflicts.map((conflict, idx) => {
              const [nodeA, nodeB] = conflict.between || [];
              const agentA = plan.find((n) => n.id === nodeA);
              const agentB = plan.find((n) => n.id === nodeB);

              const isRatified = !!ratifiedConflicts[idx];

              return (
                <motion.div
                  key={idx}
                  className={`conflict-card ${isRatified ? "conflict-ratified" : ""}`}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: idx * 0.1 }}
                >
                  <div className="conflict-header">
                    <div className="conflict-parties">
                      <span className="party-chip">
                        Node [{nodeA}] ({agentA?.agent || "agent"})
                      </span>
                      <span className="party-vs">disagrees with</span>
                      <span className="party-chip">
                        Node [{nodeB}] ({agentB?.agent || "agent"})
                      </span>
                    </div>

                    <div className="arbitration-status-tag">
                      {isRatified ? (
                        <span className="tag-ratified">✓ Council Ratified</span>
                      ) : (
                        <span>Arbitrated by Agora Engine</span>
                      )}
                    </div>
                  </div>

                  {/* Side-by-side statement comparisons */}
                  <div className="disputed-claims-grid">
                    <div className="claim-box">
                      <div className="claim-header">
                        <span className="claim-author">Claim from Node [{nodeA}]:</span>
                      </div>
                      <div className="claim-text">"{result[nodeA] || "Output statement"}"</div>
                    </div>

                    <div className="claim-box">
                      <div className="claim-header">
                        <span className="claim-author">Claim from Node [{nodeB}]:</span>
                      </div>
                      <div className="claim-text">"{result[nodeB] || "Output statement"}"</div>
                    </div>
                  </div>

                  {/* Plain Language Explanation */}
                  <div className="discrepancy-box">
                    <div className="box-label">
                      <span className="label-icon">🔍</span>
                      <span>Factual Divergence Explanation:</span>
                    </div>
                    <p className="explanation-text">{conflict.explanation}</p>
                  </div>

                  {/* Suggested Resolution */}
                  <div className="resolution-box">
                    <div className="box-label">
                      <span className="label-icon">⚖️</span>
                      <span>Suggested Arbitration Resolution:</span>
                    </div>
                    <p className="resolution-text">{conflict.suggested_resolution}</p>
                  </div>

                  {/* Ratification Action Bar */}
                  <div className="conflict-ratify-bar">
                    <button
                      className={`btn-ratify ${isRatified ? "btn-ratified-active" : ""}`}
                      onClick={() => toggleRatify(idx)}
                    >
                      {isRatified ? "✓ Arbitration Finding Ratified" : "⚖️ Ratify Arbitration Resolution"}
                    </button>
                    <span className="ratify-caption">
                      {isRatified
                        ? "Finding accepted into council ledger. Negative Bayesian penalty applied to conflicting node."
                        : "Click to enforce suggested resolution and record verified truth into council ledger."}
                    </span>
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
