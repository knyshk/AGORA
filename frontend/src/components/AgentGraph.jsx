import { useState, useRef, useLayoutEffect, useMemo, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";

const AGENT_META = {
  research: {
    label: "Research Agent",
    skill: "Gathers verifiable facts & historical data",
    color: "#e59b2c",
    bg: "rgba(229, 155, 44, 0.12)",
    border: "rgba(229, 155, 44, 0.35)",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="M20 20l-5.5-5.5" strokeLinecap="round" />
        <path d="M8 10.5h5M10.5 8v5" strokeLinecap="round" />
      </svg>
    ),
  },
  drafting: {
    label: "Drafting Agent",
    skill: "Synthesizes prose from antecedent research",
    color: "#e07a38",
    bg: "rgba(224, 122, 56, 0.12)",
    border: "rgba(224, 122, 56, 0.35)",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M4 20h4L19 9l-4-4L4 16v4z" strokeLinejoin="round" />
        <path d="M13 7l4 4" strokeLinecap="round" />
      </svg>
    ),
  },
  chart: {
    label: "Chart Agent",
    skill: "Structures numeric data into visualizations",
    color: "#d4a034",
    bg: "rgba(212, 160, 52, 0.12)",
    border: "rgba(212, 160, 52, 0.35)",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M4 20V11M10 20V6M16 20v-8M20 20v-4" strokeLinecap="round" />
        <path d="M3 20h18" strokeLinecap="round" />
      </svg>
    ),
  },
  fact_check: {
    label: "Fact-Check Agent",
    skill: "Audits assertions against source citations",
    color: "#52a373",
    bg: "rgba(82, 163, 115, 0.12)",
    border: "rgba(82, 163, 115, 0.35)",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M12 3l8 3.5v5.5c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6.5L12 3z" strokeLinejoin="round" />
        <path d="M9 12l2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
};

const DEFAULT_META = {
  label: "Specialized Agent",
  skill: "Autonomous worker node",
  color: "#c9bdab",
  bg: "rgba(201, 189, 171, 0.1)",
  border: "rgba(201, 189, 171, 0.3)",
  icon: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="8" />
    </svg>
  ),
};

function buildLevels(plan) {
  if (!plan || plan.length === 0) return [];
  const levels = [];
  const placed = new Set();
  let remaining = [...plan];
  let guard = 0;

  while (remaining.length > 0 && guard < 10) {
    guard++;
    const level = remaining.filter((node) =>
      (node.depends_on || []).every((dep) => placed.has(dep))
    );

    if (level.length === 0) {
      levels.push(remaining);
      remaining.forEach((n) => placed.add(n.id));
      break;
    }

    levels.push(level);
    level.forEach((n) => placed.add(n.id));
    remaining = remaining.filter((n) => !placed.has(n.id));
  }
  return levels;
}

export default function AgentGraph({ plan, result = {}, conflicts = [], selectedNode, onSelectNode }) {
  const containerRef = useRef(null);
  const nodeRefs = useRef({});
  const [lines, setLines] = useState([]);
  const [hoveredNode, setHoveredNode] = useState(null);
  const [hoverPos, setHoverPos] = useState(null);

  const levels = useMemo(() => buildLevels(plan), [plan]);

  const conflictedIds = useMemo(() => {
    return new Set(conflicts.flatMap((c) => c.between || []));
  }, [conflicts]);

  const nodeConflictsFor = useCallback(
    (nodeId) => conflicts.filter((c) => (c.between || []).includes(nodeId)),
    [conflicts]
  );

  const updateLines = useCallback(() => {
    if (!containerRef.current) return;
    const containerRect = containerRef.current.getBoundingClientRect();
    const newLines = [];

    (plan || []).forEach((node) => {
      const childEl = nodeRefs.current[node.id];
      if (!childEl) return;
      const childRect = childEl.getBoundingClientRect();
      const cx = childRect.left + childRect.width / 2 - containerRect.left;
      const cy = childRect.top - containerRect.top;

      (node.depends_on || []).forEach((depId) => {
        const parentEl = nodeRefs.current[depId];
        if (!parentEl) return;
        const pRect = parentEl.getBoundingClientRect();
        const px = pRect.left + pRect.width / 2 - containerRect.left;
        const py = pRect.bottom - containerRect.top;

        const isChildConflicted = conflictedIds.has(node.id);
        const isParentConflicted = conflictedIds.has(depId);
        const isConflictEdge = isChildConflicted && isParentConflicted;

        const deltaY = cy - py;
        const cp1Y = py + deltaY * 0.45;
        const cp2Y = cy - deltaY * 0.45;
        const pathData = `M ${px} ${py} C ${px} ${cp1Y}, ${cx} ${cp2Y}, ${cx} ${cy}`;

        newLines.push({
          id: `${depId}->${node.id}`,
          from: depId,
          to: node.id,
          px,
          py,
          cx,
          cy,
          pathData,
          isConflictEdge,
        });
      });
    });

    setLines(newLines);
  }, [plan, conflictedIds]);

  useLayoutEffect(() => {
    updateLines();
  }, [updateLines, levels]);

  useEffect(() => {
    const handleResize = () => updateLines();
    window.addEventListener("resize", handleResize);
    const observer = new ResizeObserver(() => updateLines());
    if (containerRef.current) observer.observe(containerRef.current);
    return () => {
      window.removeEventListener("resize", handleResize);
      observer.disconnect();
    };
  }, [updateLines]);

  const handleNodeEnter = (nodeId) => {
    setHoveredNode(nodeId);
    const el = nodeRefs.current[nodeId];
    const container = containerRef.current;
    if (el && container) {
      const elRect = el.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      setHoverPos({
        top: elRect.top - containerRect.top,
        left: elRect.left - containerRect.left + elRect.width / 2,
        width: elRect.width,
      });
    }
  };

  const handleNodeLeave = () => {
    setHoveredNode(null);
    setHoverPos(null);
  };

  const hoveredNodeData = hoveredNode ? plan.find((n) => n.id === hoveredNode) : null;
  const hoveredMeta = hoveredNodeData ? AGENT_META[hoveredNodeData.agent] || DEFAULT_META : null;
  const hoveredOutput = hoveredNode ? result[hoveredNode] : "";
  const hoveredConflicts = hoveredNode ? nodeConflictsFor(hoveredNode) : [];

  return (
    <div className="graph-wrapper">
      <div className="graph-toolbar">
        <div className="graph-topology-info">
          <span className="topology-badge">DAG Topology</span>
          <span className="topology-metrics">
            {plan.length} {plan.length === 1 ? "Node" : "Nodes"} • {lines.length} Dependency {lines.length === 1 ? "Edge" : "Edges"} • {levels.length} Execution {levels.length === 1 ? "Tier" : "Tiers"}
          </span>
        </div>

        <div className="graph-legend">
          <div className="legend-item">
            <span className="legend-dot dot-verified" />
            <span>Harmonious</span>
          </div>
          <div className="legend-item">
            <span className="legend-dot dot-conflict" />
            <span>Disputed Claim</span>
          </div>
          <div className="legend-item">
            <span className="legend-line" />
            <span>Data Dependency Flow</span>
          </div>
        </div>
      </div>

      <div className="graph-canvas" ref={containerRef}>
        <svg className="graph-svg-layer">
          <defs>
            <marker id="arrow-amber" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#e59b2c" opacity="0.8" />
            </marker>
            <marker id="arrow-conflict" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#d9534f" />
            </marker>
            <linearGradient id="edge-flow-grad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#e59b2c" stopOpacity="0.8" />
              <stop offset="100%" stopColor="#f5ab3d" stopOpacity="0.4" />
            </linearGradient>
          </defs>

          {lines.map((l) => {
            const isRelevant = hoveredNode === l.from || hoveredNode === l.to || selectedNode === l.from || selectedNode === l.to;
            const isFaded = (hoveredNode || selectedNode) && !isRelevant;

            return (
              <g key={l.id} className="edge-group">
                {isRelevant && (
                  <path d={l.pathData} className="edge-glow" stroke={l.isConflictEdge ? "#d9534f" : "#e59b2c"} strokeWidth="6" fill="none" opacity="0.3" />
                )}
                <motion.path
                  d={l.pathData}
                  className={`graph-edge ${l.isConflictEdge ? "edge-conflict" : "edge-normal"} ${isRelevant ? "edge-active" : isFaded ? "edge-dimmed" : ""}`}
                  markerEnd={l.isConflictEdge ? "url(#arrow-conflict)" : "url(#arrow-amber)"}
                  initial={{ pathLength: 0, opacity: 0 }}
                  animate={{ pathLength: 1, opacity: isFaded ? 0.2 : 0.8 }}
                  transition={{ duration: 0.6, delay: 0.2 }}
                />
                <path d={l.pathData} className="edge-flow-pulse" stroke={l.isConflictEdge ? "#ff6b6b" : "#ffc266"} strokeWidth="2" fill="none" strokeDasharray="6 14" />
              </g>
            );
          })}
        </svg>

        {levels.map((levelNodes, levelIndex) => {
          const tierLabel =
            levelIndex === 0
              ? "Tier 1 • Root Antecedents (Executed Concurrently)"
              : levelIndex === 1
              ? "Tier 2 • Dependent Synthesis (Awaiting Tier 1 Artifacts)"
              : `Tier ${levelIndex + 1} • Collation & Audit (Downstream Resolution)`;

          return (
            <div className="graph-tier-block" key={levelIndex}>
              <div className="tier-header">
                <span className="tier-indicator">T{levelIndex + 1}</span>
                <span className="tier-title">{tierLabel}</span>
              </div>

              <div className="graph-level-nodes">
                {levelNodes.map((node, nodeIndex) => {
                  const meta = AGENT_META[node.agent] || DEFAULT_META;
                  const isConflicted = conflictedIds.has(node.id);
                  const isSelected = selectedNode === node.id;
                  const isHovered = hoveredNode === node.id;
                  const nodeDelay = (levelIndex * 3 + nodeIndex) * 0.08;

                  return (
                    <motion.div
                      key={node.id}
                      ref={(el) => (nodeRefs.current[node.id] = el)}
                      className={`agent-node-card ${isConflicted ? "node-disputed" : "node-harmonious"} ${isSelected ? "node-active-ring" : ""} ${isHovered ? "node-hovered" : ""}`}
                      onClick={() => onSelectNode(node.id)}
                      onMouseEnter={() => handleNodeEnter(node.id)}
                      onMouseLeave={handleNodeLeave}
                      initial={{ opacity: 0, y: 16, scale: 0.94 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      transition={{ duration: 0.4, delay: nodeDelay }}
                      whileHover={{ y: -4, transition: { duration: 0.15 } }}
                    >
                      <div className="node-top-bar">
                        <span className="node-id-chip">[{node.id}]</span>
                        <div className="node-status-area">
                          {isConflicted ? (
                            <span className="dispute-pill" title="Contradictory factual claim detected">
                              <span className="dispute-dot" />
                              Contested
                            </span>
                          ) : (
                            <span className="verified-pill" title="Output cross-examined and consistent">
                              <span className="verified-dot" />
                              Ready
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="node-main-content">
                        <div
                          className="node-avatar"
                          style={{
                            color: isConflicted ? "#ff6b6b" : meta.color,
                            backgroundColor: isConflicted ? "rgba(217, 83, 79, 0.15)" : meta.bg,
                            borderColor: isConflicted ? "rgba(217, 83, 79, 0.4)" : meta.border,
                          }}
                        >
                          {meta.icon}
                        </div>
                        <div className="node-info">
                          <div className="node-role-name">{meta.label}</div>
                          <div className="node-role-skill">{meta.skill}</div>
                        </div>
                      </div>

                      <div className="node-footer">
                        {(node.depends_on || []).length === 0 ? (
                          <span className="dep-tag dep-root">✦ Root Node • Independent</span>
                        ) : (
                          <span className="dep-tag dep-child">↳ Inputs: {(node.depends_on || []).map((d) => `[${d}]`).join(", ")}</span>
                        )}
                      </div>

                      {isSelected && <div className="selected-indicator-border" />}
                    </motion.div>
                  );
                })}
              </div>
            </div>
          );
        })}

        {/* Hover detail panel */}
        <AnimatePresence>
          {hoveredNodeData && hoverPos && (
            <motion.div
              className="node-hover-panel"
              style={{ top: hoverPos.top, left: hoverPos.left }}
              initial={{ opacity: 0, y: -6, x: "-50%" }}
              animate={{ opacity: 1, y: -10, x: "-50%" }}
              exit={{ opacity: 0, y: -6, x: "-50%" }}
              transition={{ duration: 0.15 }}
            >
              <div className="hover-panel-header">
                <span className="hover-panel-id">[{hoveredNodeData.id}]</span>
                <span className="hover-panel-agent" style={{ color: hoveredMeta.color }}>
                  {hoveredMeta.label}
                </span>
              </div>
              <div className="hover-panel-skill">{hoveredMeta.skill}</div>
              <div className="hover-panel-row">
                <span className="hover-panel-k">Dependencies:</span>
                <span className="hover-panel-v">
                  {(hoveredNodeData.depends_on || []).length === 0
                    ? "None (root node)"
                    : hoveredNodeData.depends_on.map((d) => `[${d}]`).join(", ")}
                </span>
              </div>
              {hoveredConflicts.length > 0 && (
                <div className="hover-panel-conflict-tag">⚡ {hoveredConflicts.length} disputed claim(s)</div>
              )}
              {hoveredOutput && (
                <div className="hover-panel-preview">
                  {hoveredOutput.slice(0, 140)}
                  {hoveredOutput.length > 140 ? "…" : ""}
                </div>
              )}
              <div className="hover-panel-hint">Click node to inspect full output</div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}