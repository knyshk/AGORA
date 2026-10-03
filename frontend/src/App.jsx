import { useState } from "react";
import axios from "axios";

function App() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);

  const runTask = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setResponse(null);
    try {
      const res = await axios.post("http://127.0.0.1:8000/tasks/run", { query });
      setResponse(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "2rem", fontFamily: "sans-serif" }}>
      <h1>AGORA</h1>
      <p>Multi-Agent Orchestration Platform</p>

      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Describe a task, e.g. 'Write a short report on electric scooters with a chart'"
        rows={3}
        style={{ width: "100%", padding: "0.75rem", fontSize: "1rem" }}
      />
      <button
        onClick={runTask}
        disabled={loading}
        style={{ marginTop: "0.75rem", padding: "0.6rem 1.5rem", fontSize: "1rem", cursor: "pointer" }}
      >
        {loading ? "Running..." : "Run Task"}
      </button>

      {error && (
        <div style={{ marginTop: "1.5rem", color: "red" }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {response && (
        <div style={{ marginTop: "2rem" }}>
          <h2>Plan</h2>
          <ul>
            {response.plan.map((node) => (
              <li key={node.id}>
                <strong>{node.id}</strong> — {node.agent}
                {node.depends_on.length > 0 && ` (depends on: ${node.depends_on.join(", ")})`}
              </li>
            ))}
          </ul>

          <h2>Results</h2>
          {Object.entries(response.result).map(([id, output]) => (
            <div key={id} style={{ marginBottom: "1.5rem", padding: "1rem", background: "#f5f5f5", borderRadius: 6 }}>
              <strong>{id}</strong>
              <p style={{ whiteSpace: "pre-wrap" }}>{output}</p>
            </div>
          ))}

          <h2>Conflicts</h2>
          {response.conflicts.length === 0 ? (
            <p>No conflicts detected.</p>
          ) : (
            response.conflicts.map((c, i) => (
              <div key={i} style={{ padding: "1rem", background: "#fff0f0", border: "1px solid red", borderRadius: 6, marginBottom: "1rem" }}>
                <strong>Conflict between {c.between.join(" & ")}</strong>
                <p>{c.explanation}</p>
                <p><em>Suggested resolution: {c.suggested_resolution}</em></p>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

export default App;