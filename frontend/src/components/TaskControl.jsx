import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";

const PRESET_QUERIES = [
  {
    label: "Renewable Energy Adoption",
    query: "Compare renewable energy adoption in Germany and France with current metrics, policy differences, and 2030 projections.",
  },
  {
    label: "Solid-State vs Li-ion Batteries",
    query: "Evaluate solid-state battery technology against conventional lithium-ion, outlining energy density, safety, and production bottlenecks.",
  },
  {
    label: "Quantum Encryption Threats",
    query: "Analyze the vulnerability of RSA and ECC encryption to Shor's algorithm, detailing post-quantum cryptography migration timelines.",
  },
  {
    label: "Electric Scooters Report",
    query: "Write a short report on urban electric scooter adoption with key safety metrics and economic impacts.",
  },
];

const STAGES = [
  {
    id: 1,
    title: "Topological Decomposition",
    desc: "Planner agent parses the query into a directed acyclic graph (DAG) of specialized subtasks.",
    threshold: 0,
  },
  {
    id: 2,
    title: "Bayesian Reputation Routing",
    desc: "Querying Redis trust scores to pick optimal model variants for research, drafting, chart, and fact-check.",
    threshold: 4,
  },
  {
    id: 3,
    title: "Parallel Async Execution",
    desc: "Independent nodes run concurrently via asyncio.gather; dependent nodes await prerequisite outputs.",
    threshold: 9,
  },
  {
    id: 4,
    title: "Conflict Arbitration Chamber",
    desc: "Arbitration engine conducts pairwise cross-examination across all agent outputs to detect factual divergence.",
    threshold: 20,
  },
];

export default function TaskControl({
  query,
  setQuery,
  loading,
  loadingMode,
  onRunTask,
  onRunConflictDemo,
  onReset,
  hasResult,
  error,
}) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!loading) return;
    const start = Date.now();
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 100) / 10);
    }, 100);
    return () => {
      clearInterval(timer);
      setElapsed(0);
    };
  }, [loading]);

  const currentStageIndex = STAGES.reduce((acc, stage, idx) => {
    return elapsed >= stage.threshold ? idx : acc;
  }, 0);

  return (
    <section className="control-section">
      <div className="section-title-bar">
        <div>
          <span className="section-eyebrow">Task Orchestration</span>
          <h2 className="section-title">Convening the Assembly</h2>
        </div>
        {hasResult && !loading && (
          <button className="btn-secondary" onClick={onReset} title="Clear current run">
            Reset Plan
          </button>
        )}
      </div>

      <div className="control-card">
        {/* Preset Queries */}
        <div className="presets-wrapper">
          <span className="presets-label">Prompt Presets:</span>
          <div className="preset-chips">
            {PRESET_QUERIES.map((preset) => (
              <button
                key={preset.label}
                type="button"
                className="preset-chip"
                onClick={() => setQuery(preset.query)}
                disabled={loading}
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>

        {/* Textarea Input */}
        <div className="input-wrapper">
          <textarea
            className="task-textarea"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Instruct the council of agents — e.g. 'Compare renewable energy adoption in Germany and France with key metrics and projections'…"
            rows={3}
            disabled={loading}
          />
        </div>

        {/* Actions Row */}
        <div className="actions-bar">
          <div className="primary-actions">
            <motion.button
              type="button"
              className="btn-primary"
              onClick={onRunTask}
              disabled={loading || !query.trim()}
              whileTap={{ scale: 0.98 }}
            >
              <span className="btn-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
              </span>
              <span>{loading && loadingMode === "task" ? "Convening Council…" : "Assemble Agora & Run"}</span>
            </motion.button>

            <motion.button
              type="button"
              className="btn-conflict-demo"
              onClick={onRunConflictDemo}
              disabled={loading}
              whileTap={{ scale: 0.98 }}
              title="Runs a benchmark task with guaranteed contradictory claims to demonstrate factual arbitration"
            >
              <span className="conflict-btn-badge">Demo</span>
              <span className="btn-icon conflict-icon">⚡</span>
              <span>Trigger Conflict Arbitration Demo</span>
            </motion.button>
          </div>

          <div className="action-hint">
            <span>Independent nodes execute concurrently • Factual claims verified pairwise</span>
          </div>
        </div>

        {/* Error notification */}
        {error && (
          <motion.div
            className="error-banner"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="error-icon">⚠️</div>
            <div className="error-body">
              <strong>Execution Note:</strong> {error}
            </div>
          </motion.div>
        )}
      </div>

      {/* Intentional Loading Screen */}
      <AnimatePresence>
        {loading && (
          <motion.div
            className="loading-panel"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.3 }}
          >
            <div className="loading-header">
              <div className="loading-title-group">
                <div className="torch-flame">
                  <span className="flame-inner" />
                </div>
                <div>
                  <h3 className="loading-title">
                    {loadingMode === "conflict"
                      ? "Injecting Contradictory Claims & Convening Arbitration…"
                      : "Convening Autonomous Multi-Agent Assembly…"}
                  </h3>
                  <p className="loading-sub">
                    Multi-agent DAG execution in progress. Calls typically require 10–30s for topological planning,
                    parallel execution, and pairwise dispute verification.
                  </p>
                </div>
              </div>

              <div className="stopwatch-badge">
                <span className="stopwatch-pulse" />
                <span className="stopwatch-digits">{elapsed.toFixed(1)}s</span>
                <span className="stopwatch-label">elapsed</span>
              </div>
            </div>

            {/* Stages Tracker */}
            <div className="stages-tracker">
              {STAGES.map((stage, idx) => {
                const isActive = idx === currentStageIndex;
                const isPassed = idx < currentStageIndex;
                return (
                  <div
                    key={stage.id}
                    className={`stage-item ${isActive ? "stage-active" : isPassed ? "stage-passed" : "stage-pending"}`}
                  >
                    <div className="stage-indicator">
                      {isPassed ? (
                        <span className="stage-check">✓</span>
                      ) : isActive ? (
                        <span className="stage-pulse-dot" />
                      ) : (
                        <span className="stage-number">{stage.id}</span>
                      )}
                    </div>
                    <div className="stage-content">
                      <div className="stage-heading">{stage.title}</div>
                      <div className="stage-desc">{stage.desc}</div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Progress Bar */}
            <div className="pipeline-bar-wrapper">
              <div
                className="pipeline-bar-fill"
                style={{
                  width: `${Math.min(95, (elapsed / 26) * 100)}%`,
                }}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
