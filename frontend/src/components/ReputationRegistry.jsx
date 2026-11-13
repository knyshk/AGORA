
import { useState, useEffect } from "react";
import axios from "axios";
import { motion } from "framer-motion";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "/api"
).replace(/\/$/, "");

const apiUrl = (path) => `${API_BASE_URL}${path}`;

function numeric(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export default function ReputationRegistry() {
  const [scores, setScores] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  const loadScores = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await axios.get(
        apiUrl("/reputation/scores"),
        { timeout: 5000 }
      );

      if (
        !response.data ||
        typeof response.data !== "object" ||
        Array.isArray(response.data)
      ) {
        throw new Error(
          "The backend returned an invalid reputation response."
        );
      }

      setScores(response.data);
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (err) {
      const detail =
        err.response?.data?.detail ||
        err.response?.data?.message ||
        err.message ||
        "Unable to load reputation scores.";

      setScores(null);
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let mounted = true;

    const initialLoad = async () => {
      try {
        const response = await axios.get(
          apiUrl("/reputation/scores"),
          { timeout: 5000 }
        );

        if (
          !response.data ||
          typeof response.data !== "object" ||
          Array.isArray(response.data)
        ) {
          throw new Error(
            "The backend returned an invalid reputation response."
          );
        }

        if (mounted) {
          setScores(response.data);
          setLastUpdated(
            new Date().toLocaleTimeString()
          );
          setError(null);
        }
      } catch (err) {
        if (mounted) {
          setScores(null);
          setError(
            err.response?.data?.detail ||
            err.response?.data?.message ||
            err.message ||
            "Unable to load reputation scores."
          );
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    initialLoad();

    return () => {
      mounted = false;
    };
  }, []);

  return (
    <section className="registry-section">
      <div className="registry-header-bar">
        <div>
          <span className="section-eyebrow">
            Trust & Routing Architecture
          </span>

          <h3 className="section-title">
            Redis Reputation Registry
          </h3>
        </div>

        <div className="registry-actions">
          <span className="registry-sync-time">
            {lastUpdated
              ? `Last updated: ${lastUpdated}`
              : "Not yet synchronized"}
          </span>

          <button
            className="btn-sync"
            onClick={loadScores}
            disabled={loading}
          >
            {loading
              ? "Loading…"
              : "↻ Refresh Scores"}
          </button>
        </div>
      </div>

      <p className="registry-explainer">
        These values are fetched from the running backend.
        Sample reputation values are never substituted when
        Redis or the API is unavailable.
      </p>

      {loading && (
        <p className="registry-explainer">
          Loading live reputation scores…
        </p>
      )}

      {!loading && error && (
        <div className="error-banner" role="alert">
          <div className="error-icon">⚠️</div>

          <div className="error-body">
            <strong>Reputation data unavailable:</strong>
            {" "}
            {error}
          </div>
        </div>
      )}

      {!loading &&
        !error &&
        scores &&
        Object.keys(scores).length === 0 && (
          <p className="registry-explainer">
            No agents are registered yet.
          </p>
        )}

      {!loading &&
        !error &&
        scores &&
        Object.keys(scores).length > 0 && (
          <div className="reputation-grid">
            {Object.entries(scores).map(
              ([agentName, data], index) => {
                const score = numeric(data.score);
                const prior = numeric(data.prior);
                const successes = numeric(data.successes);
                const total = numeric(data.total);

                const successRate =
                  total !== null && total > 0
                    ? (successes / total) * 100
                    : prior !== null
                      ? prior * 100
                      : null;

                return (
                  <motion.div
                    key={agentName}
                    className="rep-card"
                    initial={{
                      opacity: 0,
                      y: 10,
                    }}
                    animate={{
                      opacity: 1,
                      y: 0,
                    }}
                    transition={{
                      duration: 0.3,
                      delay: index * 0.04,
                    }}
                  >
                    <div className="rep-card-topbar">
                      <div>
                        <span className="rep-agent-id">
                          {agentName}
                        </span>

                        <span className="rep-skill-tag">
                          {data.skill || "Unknown skill"}
                        </span>
                      </div>

                      <div className="rep-score-badge">
                        <span className="score-num">
                          {score === null
                            ? "N/A"
                            : score.toFixed(3)}
                        </span>

                        <span className="score-label">
                          Trust
                        </span>
                      </div>
                    </div>

                    <div className="rep-meter-wrapper">
                      <div
                        className="rep-meter-fill"
                        style={{
                          width: `${
                            Math.max(
                              0,
                              Math.min(
                                100,
                                (score ?? 0) * 100
                              )
                            )
                          }%`,
                        }}
                      />
                    </div>

                    <div className="rep-stats-row">
                      <div className="rep-stat-col">
                        <span className="rep-k">Prior:</span>
                        <span className="rep-v">
                          {prior === null
                            ? "N/A"
                            : prior.toFixed(2)}
                        </span>
                      </div>

                      <div className="rep-stat-col">
                        <span className="rep-k">Trials:</span>
                        <span className="rep-v">
                          {successes === null
                            ? "?"
                            : successes}
                          /
                          {total === null ? "?" : total}
                        </span>
                      </div>

                      <div className="rep-stat-col">
                        <span className="rep-k">Win Rate:</span>
                        <span className="rep-v">
                          {successRate === null
                            ? "N/A"
                            : `${successRate.toFixed(0)}%`}
                        </span>
                      </div>
                    </div>

                    <div className="rep-footer-info">
                      <span className="rep-provider">
                        Model: {data.model || "Not specified"}
                      </span>
                    </div>
                  </motion.div>
                );
              }
            )}
          </div>
        )}
    </section>
  );
}
