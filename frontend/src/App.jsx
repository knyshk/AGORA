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
import RunHistory from "./components/RunHistory";
import LiveSessions from "./components/LiveSessions";

const BACKEND_URL = "http://127.0.0.1:8000";

// Fallback verified benchmark samples for resilient demoing


export default function App() {
  const [query, setQuery] = useState(
    "Compare renewable energy adoption in Germany and France with current metrics, policy differences, and 2030 projections."
  );
  const [loading, setLoading] = useState(false);
  const [loadingMode, setLoadingMode] = useState(null); // 'task' | 'conflict'
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [backendOnline, setBackendOnline] = useState(false);
  const [checkingBackend, setCheckingBackend] = useState(true);
  const [activeTab, setActiveTab] = useState(
    () => (new URLSearchParams(window.location.search).get("join") ? "live" : "orchestrator")
  ); // 'orchestrator' | 'latency' | 'reputation' | 'history' | 'live'

  const resultsRef = useRef(null);

  // Health check on mount and interval
  useEffect(() => {
    let mounted = true;
    const checkHealth = async () => {
      try {
        const res = await axios.get(`${BACKEND_URL}/health`, { timeout: 3000 });
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

  // Run full user task via POST /tasks/run
  const handleRunTask = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setLoadingMode("task");
    setError(null);
    setResponse(null);
    setSelectedNode(null);

    try {
      const res = await axios.post(
        `${BACKEND_URL}/tasks/run`,
        { query: query.trim() },
        { timeout: 240000 }
      );
      setResponse(res.data);
      if (res.data.plan && res.data.plan.length > 0) {
        setSelectedNode(res.data.plan[0].id);
      }
      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: "smooth" });
      }, 200);
    } catch (err) {
      console.warn("Backend error or timeout on /tasks/run:", err);
      const detail =
        err.response?.data?.detail ||
        err.response?.data?.message ||
        err.message ||
        "Backend request timed out or was interrupted.";
      setError(detail);
      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: "smooth" });
      }, 200);
    } finally {
      setLoading(false);
      setLoadingMode(null);
    }
  };

  // Run conflict demo via POST /tasks/conflict-demo
  const handleRunConflictDemo = async () => {
    setLoading(true);
    setLoadingMode("conflict");
    setError(null);
    setResponse(null);
    setSelectedNode(null);

    try {
      const res = await axios.post(`${BACKEND_URL}/tasks/conflict-demo`, {}, { timeout: 60000 });
      setResponse(res.data);
      if (res.data.plan && res.data.plan.length > 0) {
        setSelectedNode(res.data.plan[0].id);
      }
      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: "smooth" });
      }, 200);
    } catch (err) {
      console.warn("Backend error or timeout on /tasks/conflict-demo:", err);
      const detail =
        err.response?.data?.detail ||
        err.message ||
        "Backend request timed out.";
      setError(detail);
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

      {/* Top Colonnade Header Bar */}
      <header className="agora-nav">
        <div className="nav-container">
          <div className="nav-brand">
            <div className="brand-emblem">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#e59b2c" strokeWidth="1.8">
                <path d="M3 21h18M5 21V9l7-5 7 5v12M9 21V12h6v9" strokeLinejoin="round" />
              </svg>
            </div>
            <div className="brand-text-block">
              <span className="brand-title">AGORA</span>
              <span className="brand-tagline">Multi-Agent AI Orchestration</span>
            </div>
          </div>

          <div className="nav-meta">
            <div className="nav-stat-chip">
              <span className="chip-key">Concurrency:</span>
              <span className="chip-val">2.68× Speedup</span>
            </div>
            <div className="nav-stat-chip">
              <span className="chip-key">Trust Scoring:</span>
              <span className="chip-val">Redis Bayesian</span>
            </div>
            <div className="nav-stat-chip">
              <span className="chip-key">Arbitration:</span>
              <span className="chip-val">Structured Claims</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="agora-main-container">
        {/* Hero Section with 4 Real Capabilities & Verified Stats */}
        <Hero backendOnline={backendOnline} checkingBackend={checkingBackend} />

        {/* Module Switcher Tabs */}
        <div className="agora-module-nav">
          <button
            className={`module-tab ${activeTab === "orchestrator" ? "module-tab-active" : ""}`}
            onClick={() => setActiveTab("orchestrator")}
          >
            <span className="tab-icon">🏛️</span>
            <span className="tab-text">Task Orchestration & DAG Floor</span>
          </button>
          <button
            className={`module-tab ${activeTab === "latency" ? "module-tab-active" : ""}`}
            onClick={() => setActiveTab("latency")}
          >
            <span className="tab-icon">⚡</span>
            <span className="tab-text">DAG Concurrency Benchmark</span>
            <span className="tab-pill">2.68× Speedup</span>
          </button>
          <button
            className={`module-tab ${activeTab === "reputation" ? "module-tab-active" : ""}`}
            onClick={() => setActiveTab("reputation")}
          >
            <span className="tab-icon">🛡️</span>
            <span className="tab-text">Redis Reputation Registry</span>
            <span className="tab-pill">Bayesian Routing</span>
          </button>
          <button
            className={`module-tab ${activeTab === "history" ? "module-tab-active" : ""}`}
            onClick={() => setActiveTab("history")}
          >
            <span className="tab-icon">🕘</span>
            <span className="tab-text">Run History & Replay</span>
            <span className="tab-pill">Fork</span>
          </button>
          <button
            className={`module-tab ${activeTab === "live" ? "module-tab-active" : ""}`}
            onClick={() => setActiveTab("live")}
          >
            <span className="tab-icon">👥</span>
            <span className="tab-text">Live Sessions</span>
            <span className="tab-pill">Collaborate</span>
          </button>
        </div>

        {/* Tab 1: Task Orchestrator & Live DAG Floor */}
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

            {/* Dynamic Execution Results Section */}
            <div ref={resultsRef}>
              <AnimatePresence mode="wait">
                {response && !loading && (
                  <motion.div
                    key="execution-results"
                    className="results-arena"
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 20 }}
                    transition={{ duration: 0.4 }}
                  >
                    {/* Visual DAG Graph Centerpiece */}
                    <div className="arena-section-header">
                      <div className="arena-title-group">
                        <span className="section-eyebrow">Visual Execution Topology</span>
                        <h2 className="arena-title">Directed Acyclic Graph (DAG) Plan</h2>
                      </div>
                      <div className="arena-hint">
                        <span>Click any agent node to inspect its verified output text</span>
                      </div>
                    </div>

                    <AgentGraph
                        plan={response.plan || []}
                        result={response.result || {}}
                        conflicts={response.conflicts || []}
                        selectedNode={selectedNode}
                        onSelectNode={setSelectedNode}
                    />

                    {/* Node Output Inspector & Conflict Arbitration Chamber */}
                    <InspectorAndConflicts
                      plan={response.plan || []}
                      result={response.result || {}}
                      conflicts={response.conflicts || []}
                      selectedNode={selectedNode}
                      onSelectNode={setSelectedNode}
                      runId={response.run_id}
                      nodeStatus={response.node_status || {}}
                      usage={response.usage || null}
                      onReviewed={(conflicts, status) => setResponse((r) => ({ ...r, conflicts, status }))}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </>
        )}

        {/* Tab 2: DAG Concurrency & Latency Benchmark */}
        {activeTab === "latency" && <LatencyBenchmark />}

        {/* Tab 3: Redis Reputation Registry */}
        {activeTab === "reputation" && <ReputationRegistry />}
        {activeTab === "history" && <RunHistory backendUrl={BACKEND_URL} />}
        {activeTab === "live" && <LiveSessions backendUrl={BACKEND_URL} />}
      </main>

      {/* Classical Agora Footer */}
      <footer className="agora-footer">
        <div className="footer-container">
          <div className="footer-left">
            <div className="footer-brand">AGORA Platform</div>
            <p className="footer-desc">
              BTech Major Project: Multi-Agent AI Orchestration, Bayesian Reputation Routing, and Conflict Arbitration.
            </p>
          </div>

          <div className="footer-specs">
            <div className="spec-row">
              <span className="spec-label">Orchestration:</span>
              <span className="spec-value">FastAPI + Asyncio DAG Execution</span>
            </div>
            <div className="spec-row">
              <span className="spec-label">Reputation:</span>
              <span className="spec-value">Redis-Backed Bayesian Thompson Sampling</span>
            </div>
            <div className="spec-row">
              <span className="spec-label">Arbitration:</span>
              <span className="spec-value">Structured Claim Arbitration + Human Review</span>
            </div>
            <div className="spec-row">
              <span className="spec-label">Frontend:</span>
              <span className="spec-value">Vite + React (Plain JS) • Multi-Agent Dashboard</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}