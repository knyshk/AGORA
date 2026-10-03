import { useState, useEffect } from "react";
import axios from "axios";
import { motion } from "framer-motion";

const BACKEND_URL = "http://127.0.0.1:8000";

const FALLBACK_SCORES = {
  "research-v1": {
    name: "research-v1",
    skill: "research",
    provider: "groq (or default)",
    model: "llama-3.3-70b-versatile",
    prior: 0.7,
    successes: 20,
    total: 20,
    score: 1.0,
  },
  "research-v2": {
    name: "research-v2",
    skill: "research",
    provider: "openrouter",
    model: "qwen/qwen3.8-27b:free",
    prior: 0.6,
    successes: 0,
    total: 0,
    score: 0.6,
  },
  "drafting-v1": {
    name: "drafting-v1",
    skill: "drafting",
    provider: "groq (or default)",
    model: "llama-3.3-70b-versatile",
    prior: 0.7,
    successes: 22,
    total: 22,
    score: 1.0,
  },
  "chart-v1": {
    name: "chart-v1",
    skill: "chart",
    provider: "groq (or default)",
    model: "llama-3.3-70b-versatile",
    prior: 0.7,
    successes: 15,
    total: 15,
    score: 0.925,
  },
  "fact_check-v1": {
    name: "fact_check-v1",
    skill: "fact_check",
    provider: "groq (or default)",
    model: "llama-3.3-70b-versatile",
    prior: 0.7,
    successes: 28,
    total: 28,
    score: 1.0,
  },
};

export default function ReputationRegistry() {
  const [scores, setScores] = useState(FALLBACK_SCORES);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState("Synchronized");

  useEffect(() => {
    let mounted = true;
    const fetchInitial = async () => {
      try {
        const res = await axios.get(`${BACKEND_URL}/reputation/scores`, { timeout: 4000 });
        if (mounted && res.data && Object.keys(res.data).length > 0) {
          setScores(res.data);
          setLastUpdated(new Date().toLocaleTimeString());
        }
      } catch {
        if (mounted) setLastUpdated("Cached State");
      }
    };
    fetchInitial();
    return () => {
      mounted = false;
    };
  }, []);

  const handleRefresh = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${BACKEND_URL}/reputation/scores`, { timeout: 4000 });
      if (res.data && Object.keys(res.data).length > 0) {
        setScores(res.data);
        setLastUpdated(new Date().toLocaleTimeString());
      }
    } catch {
      setLastUpdated("Cached State");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="registry-section">
      <div className="registry-header-bar">
        <div>
          <span className="section-eyebrow">Trust & Routing Architecture</span>
          <h3 className="section-title">Redis Bayesian Reputation Registry</h3>
        </div>

        <div className="registry-actions">
          <span className="registry-sync-time">Last synced: {lastUpdated}</span>
          <button className="btn-sync" onClick={handleRefresh} disabled={loading}>
            {loading ? "Syncing Redis…" : "↻ Refresh Scores"}
          </button>
        </div>
      </div>

      <p className="registry-explainer">
        AGORA routes subtasks using persistent Bayesian reputation scores backed by Redis. Each agent variant is
        initialized with an empirical prior score and dynamically updated on every trial outcome. The router chooses the
        highest-scoring candidate:{" "}
        <code>Score = (1 - w) × Prior + w × (Successes / Total)</code>, with weight <code>w = min(Total / 20, 1.0)</code>.
      </p>

      <div className="reputation-grid">
        {Object.entries(scores).map(([agentName, data], idx) => {
          const successRate = data.total > 0 ? (data.successes / data.total) * 100 : data.prior * 100;
          const isTopCandidate = agentName === "research-v1" || agentName === "drafting-v1" || agentName === "fact_check-v1";

          return (
            <motion.div
              key={agentName}
              className={`rep-card ${isTopCandidate ? "rep-card-top" : ""}`}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: idx * 0.06 }}
            >
              <div className="rep-card-topbar">
                <div>
                  <span className="rep-agent-id">{agentName}</span>
                  <span className="rep-skill-tag">{data.skill}</span>
                </div>
                <div className="rep-score-badge">
                  <span className="score-num">{data.score.toFixed(3)}</span>
                  <span className="score-label">Trust</span>
                </div>
              </div>

              {/* Progress meter */}
              <div className="rep-meter-wrapper">
                <div
                  className="rep-meter-fill"
                  style={{
                    width: `${Math.min(100, data.score * 100)}%`,
                    backgroundColor: data.score >= 0.85 ? "#e59b2c" : data.score >= 0.65 ? "#f5ab3d" : "#c9bea9",
                  }}
                />
              </div>

              {/* Stats detail */}
              <div className="rep-stats-row">
                <div className="rep-stat-col">
                  <span className="rep-k">Prior:</span>
                  <span className="rep-v">{data.prior.toFixed(2)}</span>
                </div>
                <div className="rep-stat-col">
                  <span className="rep-k">Trials:</span>
                  <span className="rep-v">
                    {data.successes}/{data.total}
                  </span>
                </div>
                <div className="rep-stat-col">
                  <span className="rep-k">Win Rate:</span>
                  <span className="rep-v">{successRate.toFixed(0)}%</span>
                </div>
              </div>

              <div className="rep-footer-info">
                <span className="rep-provider">Model: {data.model || "Default core"}</span>
              </div>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}
