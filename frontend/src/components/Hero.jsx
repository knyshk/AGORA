
import { motion } from "framer-motion";
import CountUp from "../CountUp";

const CAPABILITIES = [
  {
    id: "orchestration",
    title: "Dependency-Driven Orchestration",
    tag: "DAG Topology",
    body: "Tasks are decomposed into a Directed Acyclic Graph. Independent nodes can run concurrently, while dependent nodes wait for required outputs.",
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
    tag: "Redis Scoring",
    body: "Agent variants have Redis-backed scores seeded by priors and updated from execution outcomes. The current router selects the highest-scoring registered variant for a skill.",
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
    tag: "Factual Comparison",
    body: "The current arbitration engine compares agent outputs for factual disagreements and returns an explanation with a suggested resolution.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
        <path d="M12 3v18M5 7l7-4 7 4M5 7v4a7 7 0 0014 0V7" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M3 17h4M17 17h4" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: "playground",
    title: "Isolated Execution Playground",
    tag: "Current Mode",
    body: "Submit a task to the existing multi-agent pipeline or run the conflict-injection demonstration. Collaborative sessions and live handoff remain planned work.",
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

export default function Hero({
  backendOnline,
  checkingBackend,
}) {
  return (
    <section className="hero-section">
      <div className="hero-emblem-row">
        <div className="hero-pill">
          <span className="hero-pill-greek">AGORA</span>
          <span className="hero-pill-sep">•</span>
          <span className="hero-pill-sub">
            The Autonomous Council of Agents
          </span>
        </div>

        <div
          className={`backend-badge ${
            backendOnline ? "badge-online" : "badge-offline"
          }`}
        >
          <span className="backend-dot" />

          <span>
            {checkingBackend
              ? "Checking API…"
              : backendOnline
                ? "API: Online"
                : "API: Unavailable"}
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
          A multi-agent orchestration platform that decomposes
          complex tasks into dependency graphs, routes work using
          Redis-backed reputation scores, and checks agent outputs
          for factual conflicts.
        </p>
      </motion.div>

      <div className="eval-strip-container">
        <div className="eval-strip-header">
          <span className="eval-strip-title">
            Previously Reported Baseline Results
          </span>

          <span className="eval-strip-note">
            Small evaluation set from the existing project.
            Re-run before presenting these as current results.
          </span>
        </div>

        <div className="stats-strip">
          <div className="stat-card">
            <div className="stat-top">
              <span className="stat-accent-tag">
                Routing
              </span>
            </div>

            <div className="stat-value">
              <CountUp to={3} />
              <span className="stat-fraction">/3</span>
            </div>

            <div className="stat-label">
              Reported Routing Checks Passed
            </div>

            <div className="stat-caption">
              Three routing trials in the existing evaluation script.
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-top">
              <span className="stat-accent-tag">
                Conflict Recall
              </span>
            </div>

            <div className="stat-value">
              <CountUp to={3} />
              <span className="stat-fraction">/3</span>
            </div>

            <div className="stat-label">
              Reported Injected Conflicts Caught
            </div>

            <div className="stat-caption">
              Three injected conflict trials in the existing evaluation script.
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-top">
              <span className="stat-accent-tag">
                False Positives
              </span>
            </div>

            <div className="stat-value">
              <CountUp to={0} />
              <span className="stat-fraction">/3</span>
            </div>

            <div className="stat-label">
              Reported Clean Pairs Flagged
            </div>

            <div className="stat-caption">
              Three clean-pair trials. This is not a broad reliability guarantee.
            </div>
          </div>

          <div className="stat-card highlight-card">
            <div className="stat-top">
              <span className="stat-accent-tag highlight-tag">
                Concurrency
              </span>
            </div>

            <div
              className="stat-value highlight-val"
              style={{ fontSize: "clamp(24px, 3vw, 38px)" }}
            >
              Re-run
            </div>

            <div className="stat-label">
              Speedup Measurement Required
            </div>

            <div className="stat-caption">
              Historical README and UI figures differ. A fresh evaluation is required.
            </div>
          </div>
        </div>
      </div>

      <div className="capabilities-grid">
        {CAPABILITIES.map((cap, index) => (
          <motion.div
            key={cap.id}
            className="capability-card"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: 0.45,
              delay: 0.1 + index * 0.08,
            }}
            whileHover={{
              y: -3,
              transition: { duration: 0.15 },
            }}
          >
            <div className="cap-header">
              <div className="cap-icon-box">
                {cap.icon}
              </div>

              <div className="cap-greek-badge">
                {cap.tag}
              </div>
            </div>

            <h3 className="cap-title">{cap.title}</h3>
            <p className="cap-body">{cap.body}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
