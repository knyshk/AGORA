import { useState } from "react";
import { motion } from "framer-motion";

export default function LatencyBenchmark() {
  const [activeView, setActiveView] = useState("comparison"); // 'comparison' | 'interactive'
  const [simulatedNodes, setSimulatedNodes] = useState(4);

  // Measured RQ3 result: backend/bench/results/rq3_20261125T155913Z.md (20 runs per mode, none excluded)
  const PARALLEL_TIME = 4.78;
  const SEQUENTIAL_TIME = 6.56;
  const PARALLEL_CI = 0.43;
  const SEQUENTIAL_CI = 0.76;
  const SPEEDUP = SEQUENTIAL_TIME / PARALLEL_TIME;
  const SAVINGS = ((SEQUENTIAL_TIME - PARALLEL_TIME) / SEQUENTIAL_TIME) * 100;

  // Simulated interactive numbers based on slider
  const avgNodeTime = 2.15;
  const simParallel = avgNodeTime * 1.15;
  const simSequential = avgNodeTime * simulatedNodes;
  const simSpeedup = simSequential / simParallel;

  return (
    <section className="latency-section">
      <div className="latency-header-bar">
        <div>
          <span className="section-eyebrow">Performance Architecture</span>
          <h3 className="section-title">DAG Concurrency vs Sequential Execution</h3>
        </div>

        <div className="latency-tabs">
          <button
            className={`tab-btn ${activeView === "comparison" ? "tab-active" : ""}`}
            onClick={() => setActiveView("comparison")}
          >
            Measured Benchmark (20 runs per mode)
          </button>
          <button
            className={`tab-btn ${activeView === "interactive" ? "tab-active" : ""}`}
            onClick={() => setActiveView("interactive")}
          >
            What-if Calculator (illustration)
          </button>
        </div>
      </div>

      {activeView === "comparison" ? (
        <div className="benchmark-card">
          <div className="benchmark-stats-strip">
            <div className="b-stat">
              <span className="b-stat-k">Parallel Latency</span>
              <span className="b-stat-v highlight-amber">{PARALLEL_TIME.toFixed(2)}s</span>
              <span className="b-stat-sub">± {PARALLEL_CI} s (95% CI) · drafting and chart run together</span>
            </div>
            <div className="b-stat">
              <span className="b-stat-k">Sequential Baseline</span>
              <span className="b-stat-v">{SEQUENTIAL_TIME.toFixed(2)}s</span>
              <span className="b-stat-sub">± {SEQUENTIAL_CI} s (95% CI) · same plan, one node at a time</span>
            </div>
            <div className="b-stat">
              <span className="b-stat-k">Observed Speedup</span>
              <span className="b-stat-v highlight-gold">{SPEEDUP.toFixed(2)}×</span>
              <span className="b-stat-sub">{SAVINGS.toFixed(1)}% less wall-clock time · maximum possible here is 2×</span>
            </div>
          </div>

          {/* Timeline visualization */}
          <div className="timeline-block">
            {/* Parallel Track */}
            <div className="timeline-track">
              <div className="track-label-area">
                <span className="track-title">AGORA Parallel DAG</span>
                <span className="track-duration">mean {PARALLEL_TIME} s</span>
              </div>
              <div className="track-bar-container">
                <motion.div
                  className="gantt-bar gantt-parallel"
                  initial={{ width: 0 }}
                  animate={{ width: `${(PARALLEL_TIME / SEQUENTIAL_TIME) * 100}%` }}
                  transition={{ duration: 0.8, ease: "easeOut" }}
                >
                  <div className="gantt-subnode">Drafting</div>
                  <div className="gantt-subnode">Chart</div>
                  <span>run at the same time</span>
                </motion.div>
                <div className="concurrency-callout">asyncio.gather</div>
              </div>
            </div>

            {/* Sequential Track */}
            <div className="timeline-track">
              <div className="track-label-area">
                <span className="track-title">Standard Sequential Baseline</span>
                <span className="track-duration">mean {SEQUENTIAL_TIME} s</span>
              </div>
              <div className="track-bar-container">
                <div className="gantt-bar gantt-sequential" style={{ gridTemplateColumns: "1fr 1fr" }}>
                  <div className="gantt-segment seg-1">Drafting</div>
                  <div className="gantt-segment seg-2">then Chart</div>
                </div>
              </div>
            </div>
          </div>
          <p style={{ fontSize: 13, opacity: 0.8, marginTop: 14, lineHeight: 1.6 }}>
            Plan: research (same frozen input every run) → drafting and chart. Agents pinned (drafting-v1, chart-v1, Groq),
            modes alternated run by run, conflict checks off. Mean of 20 runs per mode; no runs excluded. The gain is limited by
            the slower of the two branches, so 2× is the ceiling for this plan. (The mid-term showed 2.68× from only 3 trials.)
          </p>
        </div>
      ) : (
        <div className="interactive-calc-card">
          <div className="calc-controls">
            <label className="calc-label">
              <span>Simulated Independent DAG Nodes:</span>
              <strong className="calc-value">{simulatedNodes} Agents</strong>
            </label>
            <input
              type="range"
              min="2"
              max="10"
              value={simulatedNodes}
              onChange={(e) => setSimulatedNodes(Number(e.target.value))}
              className="calc-slider"
            />
          </div>

          <div className="calc-results-grid">
            <div className="calc-stat-box">
              <span className="c-label">Parallel Wall-Clock:</span>
              <span className="c-num highlight-amber">{simParallel.toFixed(2)}s</span>
              <span className="c-sub">Limited by slowest parallel node</span>
            </div>
            <div className="calc-stat-box">
              <span className="c-label">Sequential Wall-Clock:</span>
              <span className="c-num">{simSequential.toFixed(2)}s</span>
              <span className="c-sub">Accumulates latency of all {simulatedNodes} nodes</span>
            </div>
            <div className="calc-stat-box highlight-box">
              <span className="c-label">Estimated Speedup:</span>
              <span className="c-num highlight-gold">{simSpeedup.toFixed(2)}×</span>
              <span className="c-sub">{(simSequential - simParallel).toFixed(2)}s saved for user</span>
            </div>
          </div>
        </div>
      )}
      {activeView === "interactive" && (
        <p style={{ fontSize: 13, opacity: 0.8, marginTop: 12, lineHeight: 1.6 }}>
          Illustration only, not a measurement: it assumes every node takes 2.15 s and that parallel nodes do not slow each
          other down. Real runs gain less (rate limits, uneven branches); see the measured benchmark.
        </p>
      )}
    </section>
  );
}
