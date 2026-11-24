import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { motion } from "framer-motion";

const BACKEND_URL = "http://127.0.0.1:8000";
const SKILLS = ["research", "drafting", "chart", "fact_check"];

const fmt = (v, digits = 3) => (v === null || v === undefined ? "—" : Number(v).toFixed(digits));

export default function ReputationRegistry() {
  const [scores, setScores] = useState({});
  const [routes, setRoutes] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${BACKEND_URL}/reputation/scores`, { timeout: 6000 });
      const routeRes = await Promise.all(
        SKILLS.map((s) => axios.get(`${BACKEND_URL}/reputation/route`, { params: { skill: s, mode: "greedy" }, timeout: 6000 }))
      );
      setScores(res.data || {});
      setRoutes(Object.fromEntries(SKILLS.map((s, i) => [s, routeRes[i].data])));
      setError(null);
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (e) {
      setError(`Could not load reputation from the backend: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const leaders = new Set(Object.values(routes).map((r) => r.chosen));

  return (
    <section className="registry-section">
      <div className="registry-header-bar">
        <div>
          <span className="section-eyebrow">Trust & Routing Architecture</span>
          <h3 className="section-title">Bayesian Reputation Registry</h3>
        </div>

        <div className="registry-actions">
          <span className="registry-sync-time">Last synced: {lastUpdated || "never"}</span>
          <button className="btn-sync" onClick={load} disabled={loading}>
            {loading ? "Loading…" : "↻ Refresh Scores"}
          </button>
        </div>
      </div>

      <p className="registry-explainer">
        Each agent's trust is a Beta distribution: a prior worth 10 observations, plus graded evidence from every
        run. Output quality (0–1) comes from the agents' own checks — grounded chart values, the citation check,
        sources found, claims verified — and fact-check verdicts also grade the drafting agent that wrote the
        claims. Older evidence decays (×0.97 per update); rate limits and timeouts never count. The router uses{" "}
        <code>Thompson sampling × speed fit</code>.
      </p>

      {error && <div style={{ color: "#ff9187", margin: "12px 0" }}>{error}</div>}

      {Object.keys(routes).length > 0 && (
        <div style={{ margin: "12px 0 18px", fontSize: 13, lineHeight: 1.6 }}>
          <b>Current best agent per skill (by mean trust × speed):</b>
          {SKILLS.filter((s) => routes[s]).map((s) => (
            <div key={s} style={{ opacity: 0.9 }}>
              <span style={{ color: "#f5ab3d" }}>{s}</span>: {routes[s].reason}
            </div>
          ))}
        </div>
      )}

      <div className="reputation-grid">
        {Object.entries(scores).map(([agentName, data], idx) => (
          <motion.div
            key={agentName}
            className={`rep-card ${leaders.has(agentName) ? "rep-card-top" : ""}`}
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
                <span className="score-num">{fmt(data.mean)}</span>
                <span className="score-label">Trust</span>
              </div>
            </div>

            <div className="rep-meter-wrapper" title={`95% interval ${data.ci95?.[0]}–${data.ci95?.[1]}`}>
              <div
                className="rep-meter-fill"
                style={{
                  width: `${Math.min(100, data.mean * 100)}%`,
                  backgroundColor: data.mean >= 0.85 ? "#e59b2c" : data.mean >= 0.65 ? "#f5ab3d" : "#c9bea9",
                }}
              />
            </div>

            <div className="rep-stats-row">
              <div className="rep-stat-col">
                <span className="rep-k">95% CI:</span>
                <span className="rep-v">{fmt(data.ci95?.[0], 2)}–{fmt(data.ci95?.[1], 2)}</span>
              </div>
              <div className="rep-stat-col">
                <span className="rep-k">Graded runs:</span>
                <span className="rep-v">{data.n}</span>
              </div>
              <div className="rep-stat-col">
                <span className="rep-k">Avg quality:</span>
                <span className="rep-v">{fmt(data.avg_quality, 2)}</span>
              </div>
            </div>
            <div className="rep-stats-row">
              <div className="rep-stat-col">
                <span className="rep-k">Prior:</span>
                <span className="rep-v">{fmt(data.prior, 2)}</span>
              </div>
              <div className="rep-stat-col">
                <span className="rep-k">Latency:</span>
                <span className="rep-v">{data.latency_s ? `${data.latency_s}s` : "—"}</span>
              </div>
              <div className="rep-stat-col">
                <span className="rep-k">Strategy:</span>
                <span className="rep-v">{data.strategy}</span>
              </div>
            </div>

            <div className="rep-footer-info">
              <span className="rep-provider">
                {data.provider === "ollama" ? "🖥 local on this laptop" : data.provider} · {data.model}
              </span>
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
