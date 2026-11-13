
import { useState, useEffect, useRef } from "react";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import NetworkBackground from "./components/NetworkBackground";
import Hero from "./components/Hero";
import TaskControl from "./components/TaskControl";
import AgentGraph from "./components/AgentGraph";
import InspectorAndConflicts from "./components/InspectorAndConflicts";
import ReputationRegistry from "./components/ReputationRegistry";
import LatencyBenchmark from "./components/LatencyBenchmark";
import "./App.css";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "/api"
).replace(/\/$/, "");

const apiUrl = (path) => `${API_BASE_URL}${path}`;

export default function App() {
  const [query, setQuery] = useState(
    "Compare renewable energy adoption in Germany and France with current metrics, policy differences, and 2030 projections."
  );

  const [loading, setLoading] = useState(false);
  const [loadingMode, setLoadingMode] = useState(null);
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [backendOnline, setBackendOnline] = useState(false);
  const [checkingBackend, setCheckingBackend] = useState(true);
  const [activeTab, setActiveTab] = useState("orchestrator");

  const resultsRef = useRef(null);

  useEffect(() => {
    let mounted = true;

    const checkHealth = async () => {
      try {
        const res = await axios.get(apiUrl("/health"), {
          timeout: 3000,
        });

        if (mounted) {
          setBackendOnline(res.data?.status === "ok");
          setCheckingBackend(false);
        }
      } catch {
        if (mounted) {
          setBackendOnline(false);
          setCheckingBackend(false);
        }
      }
    };

    checkHealth();

    const interval = setInterval(checkHealth, 12000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  const showExecution = (data) => {
    if (
      !data ||
      !Array.isArray(data.plan) ||
      data.plan.length === 0
    ) {
      throw new Error(
        "The backend returned an invalid execution response."
      );
    }

    setResponse(data);
    setSelectedNode(data.plan[0].id);

    setTimeout(() => {
      resultsRef.current?.scrollIntoView({
        behavior: "smooth",
      });
    }, 200);
  };

  const handleRunTask = async () => {
    if (!query.trim() || loading) return;

    setLoading(true);
    setLoadingMode("task");
    setError(null);
    setResponse(null);
    setSelectedNode(null);

    try {
      const res = await axios.post(
        apiUrl("/tasks/run"),
        {
          query: query.trim(),
        },
        {
          timeout: 240000,
        }
      );

      showExecution(res.data);
    } catch (err) {
      console.error("Task execution failed:", err);

      const detail =
        err.response?.data?.detail ||
        err.response?.data?.message ||
        err.message ||
        "The backend request failed.";

      setError(
        `Task execution failed. No sample result was substituted. Details: ${detail}`
      );

      setResponse(null);
    } finally {
      setLoading(false);
      setLoadingMode(null);
    }
  };

  const handleRunConflictDemo = async () => {
    if (loading) return;

    setLoading(true);
    setLoadingMode("conflict");
    setError(null);
    setResponse(null);
    setSelectedNode(null);

    try {
      const res = await axios.post(
        apiUrl("/tasks/conflict-demo"),
        {},
        {
          timeout: 60000,
        }
      );

      showExecution(res.data);
    } catch (err) {
      console.error(
        "Conflict demonstration failed:",
        err
      );

      const detail =
        err.response?.data?.detail ||
        err.response?.data?.message ||
        err.message ||
        "The backend request failed.";

      setError(
        `Conflict demonstration failed. No sample result was substituted. Details: ${detail}`
      );

      setResponse(null);
    } finally {
      setLoading(false);
      setLoadingMode(null);
    }
  };

  const handleReset = () => {
    setResponse(null);
    setSelectedNode(null);
    setError(null);
  };

  return (
    <div className="agora-viewport">
      <NetworkBackground />

      <header className="agora-nav">
        <div className="nav-container">
          <div className="nav-brand">
            <div className="brand-emblem">
              <svg
                viewBox="0 0 24 24"
                width="20"
                height="20"
                fill="none"
                stroke="#e59b2c"
                strokeWidth="1.8"
              >
                <path
                  d="M3 21h18M5 21V9l7-5 7 5v12M9 21V12h6v9"
                  strokeLinejoin="round"
                />
              </svg>
            </div>

            <div className="brand-text-block">
              <span className="brand-title">AGORA</span>
              <span className="brand-tagline">
                Multi-Agent AI Orchestration
              </span>
            </div>
          </div>

          <div className="nav-meta">
            <div className="nav-stat-chip">
              <span className="chip-key">Concurrency:</span>
              <span className="chip-val">
                Rebenchmark required
              </span>
            </div>

            <div className="nav-stat-chip">
              <span className="chip-key">Trust Scoring:</span>
              <span className="chip-val">Redis-backed</span>
            </div>

            <div className="nav-stat-chip">
              <span className="chip-key">Arbitration:</span>
              <span className="chip-val">Pairwise audit</span>
            </div>
          </div>
        </div>
      </header>

      <main className="agora-main-container">
        <Hero
          backendOnline={backendOnline}
          checkingBackend={checkingBackend}
        />

        <div className="agora-module-nav">
          <button
            className={`module-tab ${
              activeTab === "orchestrator"
                ? "module-tab-active"
                : ""
            }`}
            onClick={() => setActiveTab("orchestrator")}
          >
            <span className="tab-icon">🏛️</span>
            <span className="tab-text">
              Task Orchestration & DAG Floor
            </span>
          </button>

          <button
            className={`module-tab ${
              activeTab === "latency"
                ? "module-tab-active"
                : ""
            }`}
            onClick={() => setActiveTab("latency")}
          >
            <span className="tab-icon">⚡</span>
            <span className="tab-text">
              DAG Concurrency Benchmark
            </span>
          </button>

          <button
            className={`module-tab ${
              activeTab === "reputation"
                ? "module-tab-active"
                : ""
            }`}
            onClick={() => setActiveTab("reputation")}
          >
            <span className="tab-icon">🛡️</span>
            <span className="tab-text">
              Redis Reputation Registry
            </span>
          </button>
        </div>

        {activeTab === "orchestrator" && (
          <>
            <TaskControl
              query={query}
              setQuery={setQuery}
              loading={loading}
              loadingMode={loadingMode}
              onRunTask={handleRunTask}
              onRunConflictDemo={handleRunConflictDemo}
              onReset={handleReset}
              hasResult={!!response}
              error={error}
            />

            <div ref={resultsRef}>
              <AnimatePresence mode="wait">
                {response && !loading && (
                  <motion.div
                    key="execution-results"
                    className="results-arena"
                    initial={{
                      opacity: 0,
                      y: 20,
                    }}
                    animate={{
                      opacity: 1,
                      y: 0,
                    }}
                    exit={{
                      opacity: 0,
                      y: 20,
                    }}
                    transition={{
                      duration: 0.4,
                    }}
                  >
                    <div className="arena-section-header">
                      <div className="arena-title-group">
                        <span className="section-eyebrow">
                          Visual Execution Topology
                        </span>

                        <h2 className="arena-title">
                          Directed Acyclic Graph (DAG) Plan
                        </h2>
                      </div>

                      <div className="arena-hint">
                        <span>
                          Select an agent node to inspect its output.
                        </span>
                      </div>
                    </div>

                    <AgentGraph
                      plan={response.plan || []}
                      result={response.result || {}}
                      conflicts={response.conflicts || []}
                      selectedNode={selectedNode}
                      onSelectNode={setSelectedNode}
                    />

                    <InspectorAndConflicts
                      plan={response.plan || []}
                      result={response.result || {}}
                      conflicts={response.conflicts || []}
                      selectedNode={selectedNode}
                      onSelectNode={setSelectedNode}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </>
        )}

        {activeTab === "latency" && (
          <LatencyBenchmark />
        )}

        {activeTab === "reputation" && (
          <ReputationRegistry />
        )}
      </main>

      <footer className="agora-footer">
        <div className="footer-container">
          <div className="footer-left">
            <div className="footer-brand">
              AGORA Platform
            </div>

            <p className="footer-desc">
              BTech Major Project: Multi-Agent AI Orchestration,
              Reputation Routing, and Conflict Arbitration.
            </p>
          </div>

          <div className="footer-specs">
            <div className="spec-row">
              <span className="spec-label">Orchestration:</span>
              <span className="spec-value">
                FastAPI + Asyncio DAG Execution
              </span>
            </div>

            <div className="spec-row">
              <span className="spec-label">Reputation:</span>
              <span className="spec-value">
                Redis-backed agent scoring
              </span>
            </div>

            <div className="spec-row">
              <span className="spec-label">Arbitration:</span>
              <span className="spec-value">
                Pairwise factual consistency engine
              </span>
            </div>

            <div className="spec-row">
              <span className="spec-label">Frontend:</span>
              <span className="spec-value">
                Vite + React dashboard
              </span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
