import { motion } from "framer-motion";
import CountUp from "../CountUp";

const CAPABILITIES = [
  {
    id: "orchestration",
    title: "Dependency-Driven Orchestration",
    tag: "DAG Topology",
    body: "Tasks compile into a Directed Acyclic Graph (DAG). Independent agent nodes execute concurrently in parallel, while dependent nodes suspend until their prerequisite artifacts are delivered.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
        <circle cx="6" cy="6" r="3" />
        <circle cx="18" cy="6" r="3" />
        <circle cx="12" cy="18" r="3" />
        <path d="M8.5 7.5L10.5 15.5M15.5 7.5L13.5 15.5M9 6h6" strokeLinecap="round" strokeDasharray="1.5 2.5" />
      </svg>
    ),
  },
  {
    id: "routing",
    title: "Reputation-Weighted Routing",
    tag: "Bayesian Scoring",
    body: "Every specialized agent carries a persistent Redis-backed trust score, updated via Bayesian Thompson sampling from real task outcomes to dynamically route steps to the highest-performing variant.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
        <path d="M12 2l2.8 6.2 6.7.7-5 4.6 1.4 6.7L12 16.8 6.1 20.2l1.4-6.7-5-4.6 6.7-.7L12 2z" strokeLinejoin="round" />
        <circle cx="12" cy="12" r="2" fill="currentColor" opacity="0.3" />
      </svg>
    ),
  },
  {
    id: "arbitration",
    title: "Conflict Arbitration Engine",
    tag: "Arbitration",
    body: "When parallel agents generate contradictory claims, our arbitration engine intercepts the divergence, produces a plain-language explanation of the disagreement, and prescribes a resolution.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
        <path d="M12 3v18M5 7l7-4 7 4M5 7v4a7 7 0 0014 0V7" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M3 17h4M17 17h4" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: "playground",
    title: "Dual-Mode Playground",
    tag: "Interactive Suite",
    body: "Execute dynamic real-world prompts through the full multi-agent pipeline, or instantly trigger the isolated Conflict Demo to observe guaranteed factual collision and dispute arbitration in action.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
        <rect x="3" y="4" width="8" height="7" rx="1.5" />
        <rect x="13" y="4" width="8" height="7" rx="1.5" />
        <rect x="8" y="14" width="8" height="7" rx="1.5" />
        <path d="M7 11v1.5a1.5 1.5 0 001.5 1.5H10M17 11v1.5a1.5 1.5 0 01-1.5 1.5H14" />
      </svg>
    ),
  },
];

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
          <span className="eval-strip-title">Verified Empirical Benchmarks</span>
          <span className="eval-strip-note">Measured on live trials across multi-agent pipelines</span>
        </div>
        <div className="stats-strip">
          <div className="stat-card">
            <div className="stat-top">
              <span className="stat-accent-tag">Bayesian Routing</span>
            </div>
            <div className="stat-value">
              <CountUp to={3} />
              <span className="stat-fraction">/3</span>
            </div>
            <div className="stat-label">Routing Decisions Correct</div>
            <div className="stat-caption">100% accuracy steering work to best-performing agent variants</div>
          </div>

          <div className="stat-card">
            <div className="stat-top">
              <span className="stat-accent-tag">Arbitration Recall</span>
            </div>
            <div className="stat-value">
              <CountUp to={3} />
              <span className="stat-fraction">/3</span>
            </div>
            <div className="stat-label">Real Conflicts Caught</div>
            <div className="stat-caption">100% recall intercepting injected factual discrepancies</div>
          </div>

          <div className="stat-card">
            <div className="stat-top">
              <span className="stat-accent-tag">Precision Balance</span>
            </div>
            <div className="stat-value">
              <CountUp to={0} />
              <span className="stat-fraction">/3</span>
            </div>
            <div className="stat-label">False Positives</div>
            <div className="stat-caption">Zero clean statements wrongly flagged as conflicting</div>
          </div>

          <div className="stat-card highlight-card">
            <div className="stat-top">
              <span className="stat-accent-tag highlight-tag">DAG Concurrency</span>
            </div>
            <div className="stat-value highlight-val">
              <CountUp to={2.68} decimals={2} suffix="×" />
            </div>
            <div className="stat-label">Parallel Execution Speedup</div>
            <div className="stat-caption">2.53s parallel vs 6.79s sequential (62.7% latency reduction)</div>
          </div>
        </div>
      </div>

      {/* 4 Real Capabilities */}
      <div className="capabilities-grid">
        {CAPABILITIES.map((cap, i) => (
          <motion.div
            key={cap.id}
            className="capability-card"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.1 + i * 0.08 }}
            whileHover={{ y: -3, transition: { duration: 0.15 } }}
          >
            <div className="cap-header">
              <div className="cap-icon-box">{cap.icon}</div>
              <div className="cap-greek-badge">{cap.tag}</div>
            </div>
            <h3 className="cap-title">{cap.title}</h3>
            <p className="cap-body">{cap.body}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
