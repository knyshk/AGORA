import { useState } from "react";
import { motion } from "framer-motion";

export default function LatencyBenchmark() {
  const [activeView, setActiveView] = useState("comparison"); // 'comparison' | 'interactive'
  const [simulatedNodes, setSimulatedNodes] = useState(4);

  // Verified benchmark numbers from evaluate.py
  const PARALLEL_TIME = 2.53;
  const SEQUENTIAL_TIME = 6.79;
  const SPEEDUP = 2.68;
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
            Verified Benchmark (3 Trials)
          </button>
          <button
            className={`tab-btn ${activeView === "interactive" ? "tab-active" : ""}`}
            onClick={() => setActiveView("interactive")}
          >
            Concurrency Scaling Calculator
          </button>
        </div>
      </div>

      {activeView === "comparison" ? (
        <div className="benchmark-card">
          <div className="benchmark-stats-strip">
            <div className="b-stat">
              <span className="b-stat-k">Parallel Latency</span>
              <span className="b-stat-v highlight-amber">{PARALLEL_TIME.toFixed(2)}s</span>
              <span className="b-stat-sub">Independent nodes run concurrently</span>
            </div>
            <div className="b-stat">
              <span className="b-stat-k">Sequential Baseline</span>
              <span className="b-stat-v">{SEQUENTIAL_TIME.toFixed(2)}s</span>
              <span className="b-stat-sub">Linear synchronous execution</span>
            </div>
            <div className="b-stat">
              <span className="b-stat-k">Observed Speedup</span>
              <span className="b-stat-v highlight-gold">{SPEEDUP.toFixed(2)}×</span>
              <span className="b-stat-sub">{SAVINGS.toFixed(1)}% total wall-clock reduction</span>
            </div>
          </div>

          {/* Timeline visualization */}
          <div className="timeline-block">
            {/* Parallel Track */}
            <div className="timeline-track">
              <div className="track-label-area">
                <span className="track-title">AGORA Parallel DAG</span>
                <span className="track-duration">{PARALLEL_TIME}s total</span>
              </div>
              <div className="track-bar-container">
                <motion.div
                  className="gantt-bar gantt-parallel"
                  initial={{ width: 0 }}
                  animate={{ width: `${(PARALLEL_TIME / SEQUENTIAL_TIME) * 100}%` }}
                  transition={{ duration: 0.8, ease: "easeOut" }}
                >
                  <div className="gantt-subnode">x1 (Research) 2.1s</div>
                  <div className="gantt-subnode">x2 (Drafting) 2.4s</div>
                  <div className="gantt-subnode">x3 (Chart) 2.5s</div>
                </motion.div>
                <div className="concurrency-callout">Concurrent Async Workers via asyncio.gather</div>
              </div>
            </div>

            {/* Sequential Track */}
            <div className="timeline-track">
              <div className="track-label-area">
                <span className="track-title">Standard Sequential Baseline</span>
                <span className="track-duration">{SEQUENTIAL_TIME}s total</span>
              </div>
              <div className="track-bar-container">
                <div className="gantt-bar gantt-sequential">
                  <div className="gantt-segment seg-1">x1: 2.1s</div>
                  <div className="gantt-segment seg-2">x2: 2.4s</div>
                  <div className="gantt-segment seg-3">x3: 2.3s</div>
                </div>
              </div>
            </div>
          </div>
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
    </section>
  );
}
