import { motion } from "framer-motion";
import CountUp from "../CountUp";

export default function Hero({ backendOnline, checkingBackend }) {
  return (
    <section className="hero-section">
      <div className="hero-emblem-row">
        <div className="hero-pill">
          <span className="hero-pill-greek">AGORA</span>
          <span className="hero-pill-sep">•</span>
          <span className="hero-pill-sub">The Autonomous Council of Agents</span>
        </div>

        <div className={`backend-badge ${backendOnline ? "badge-online" : "badge-offline"}`}>
          <span className="backend-dot" />
          <span>
            {checkingBackend
              ? "Checking Backend…"
              : backendOnline
              ? "FastAPI Engine: Online (:8000)"
              : "Backend Offline (:8000)"}
          </span>
        </div>
      </div>

      <motion.div
        className="hero-main"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
      >
        <div className="hero-title-group">
          <div className="classical-flourish-left" />
          <h1 className="hero-title">AGORA</h1>
          <div className="classical-flourish-right" />
        </div>

        <p className="hero-description">
          A multi-agent orchestration architecture that decomposes complex tasks into dependency DAGs,
          steers execution through Redis-backed Bayesian reputation scores, and intercepts factual
          disagreements between agent outputs through a live arbitration engine.
        </p>
      </motion.div>

      {/* Verified Evaluation Metrics Strip */}
      <div className="eval-strip-container">
        <div className="eval-strip-header">
          <span className="eval-strip-title">Measured Results (final evaluation)</span>
          <span className="eval-strip-note">From docs/EVALUATION.md · sample size given with every number</span>
        </div>
        <div className="stats-strip">
          <div className="stat-card">
            <div className="stat-top">
              <span className="stat-accent-tag">Conflict Detection</span>
            </div>
            <div className="stat-value">
              <CountUp to={0.984} decimals={3} />
            </div>
            <div className="stat-label">F1 on 64 Labelled Pairs</div>
            <div className="stat-caption">Structured claims vs 0.970 for the pairwise-LLM baseline (cloud model)</div>
          </div>

          <div className="stat-card">
            <div className="stat-top">
              <span className="stat-accent-tag">Precision</span>
            </div>
            <div className="stat-value">
              <CountUp to={0} />
              <span className="stat-fraction">/32</span>
            </div>
            <div className="stat-label">False Positives</div>
            <div className="stat-caption">No clean pair among the 32 hard negatives wrongly flagged as a conflict</div>
          </div>

          <div className="stat-card">
            <div className="stat-top">
              <span className="stat-accent-tag">Bayesian Routing</span>
            </div>
            <div className="stat-value">
              <CountUp to={40} />
              <span className="stat-fraction"> tasks</span>
            </div>
            <div className="stat-label">AGORA-Bench Trust Priors</div>
            <div className="stat-caption">Priors are accurate from task 1; usage-only scoring needs ≈ 95 tasks (simulation, 600 tasks × 30 seeds)</div>
          </div>

          <div className="stat-card highlight-card">
            <div className="stat-top">
              <span className="stat-accent-tag highlight-tag">DAG Concurrency</span>
            </div>
            <div className="stat-value highlight-val">
              <CountUp to={1.37} decimals={2} suffix="×" />
            </div>
            <div className="stat-label">Parallel Execution Speedup</div>
            <div className="stat-caption">4.78 s parallel vs 6.56 s sequential, 20 runs per mode (27% latency reduction)</div>
          </div>
        </div>
      </div>

    </section>
  );
}
