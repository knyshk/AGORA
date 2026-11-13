
import { useState } from "react";

export default function LatencyBenchmark() {
  const [simulatedNodes, setSimulatedNodes] = useState(4);

  // Illustrative assumptions only, not measured AGORA timings.
  const assumedNodeSeconds = 2.15;
  const orchestrationOverheadFactor = 1.15;

  const simulatedParallel =
    assumedNodeSeconds * orchestrationOverheadFactor;

  const simulatedSequential =
    assumedNodeSeconds * simulatedNodes;

  const simulatedSpeedup =
    simulatedSequential / simulatedParallel;

  return (
    <section className="latency-section">
      <div className="latency-header-bar">
        <div>
          <span className="section-eyebrow">
            Performance Architecture
          </span>

          <h3 className="section-title">
            DAG Concurrency Evaluation
          </h3>
        </div>
      </div>

      <div className="benchmark-card">
        <h3>Fresh benchmark required</h3>

        <p>
          The existing README reports a 2.76× speedup,
          while an older frontend component displays 2.68×.
          These values are inconsistent.
        </p>

        <p>
          This screen intentionally does not present either
          number as a current verified measurement.
          Run the evaluation script against the current code
          before publishing a speedup figure.
        </p>

        <pre>
{`cd backend
python evaluate.py`}
        </pre>

        <p>
          The current evaluation script uses live model calls.
          It consumes provider quota and is not a deterministic
          unit test.
        </p>
      </div>

      <div className="interactive-calc-card">
        <div className="calc-controls">
          <label className="calc-label">
            <span>Illustrative independent nodes:</span>

            <strong className="calc-value">
              {simulatedNodes} nodes
            </strong>
          </label>

          <input
            type="range"
            min="2"
            max="10"
            value={simulatedNodes}
            onChange={(event) =>
              setSimulatedNodes(Number(event.target.value))
            }
            className="calc-slider"
          />
        </div>

        <p>
          Simulation only. Each node is assumed to take{" "}
          {assumedNodeSeconds.toFixed(2)} seconds. Parallel
          execution is assumed to add{" "}
          {((orchestrationOverheadFactor - 1) * 100).toFixed(0)}%
          overhead. Real dependencies, provider limits and
          network latency are not modelled.
        </p>

        <div className="calc-results-grid">
          <div className="calc-stat-box">
            <span className="c-label">
              Simulated parallel time
            </span>

            <span className="c-num highlight-amber">
              {simulatedParallel.toFixed(2)}s
            </span>

            <span className="c-sub">
              Idealized independent-node case
            </span>
          </div>

          <div className="calc-stat-box">
            <span className="c-label">
              Simulated sequential time
            </span>

            <span className="c-num">
              {simulatedSequential.toFixed(2)}s
            </span>

            <span className="c-sub">
              Sum of assumed node durations
            </span>
          </div>

          <div className="calc-stat-box highlight-box">
            <span className="c-label">
              Illustrative speedup
            </span>

            <span className="c-num highlight-gold">
              {simulatedSpeedup.toFixed(2)}×
            </span>

            <span className="c-sub">
              Not an observed AGORA result
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
