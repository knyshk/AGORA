import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import NodeOutput from "./NodeOutput";

const GOLD = "#f5ab3d";
const PANEL = "#241c14";
const LINE = "rgba(245,171,61,0.25)";
const TEXT = "#f1e8da";
const STATUS_COLORS = { done: "#79d48b", running: GOLD, waiting: "#7fb2ff", failed: "#ff9187", skipped: "#8a8278", pending: "#8a8278" };

const card = { background: PANEL, border: `1px solid ${LINE}`, borderRadius: 12, padding: 16, marginBottom: 16, color: TEXT };
const button = { background: GOLD, color: "#0e0c0a", border: "none", borderRadius: 8, padding: "7px 12px", fontWeight: 600, cursor: "pointer" };
const ghost = { ...button, background: "transparent", color: GOLD, border: `1px solid ${LINE}` };
const input = { background: "#0e0c0a", color: TEXT, border: `1px solid ${LINE}`, borderRadius: 8, padding: "8px 10px" };
const AUTH_KEY = "agora_auth";

const QUIET = new Set(["claims_extracted", "agent_routed", "reputation_updated"]);

function errText(e) {
  return e.response?.data?.detail || e.message;
}

// Node state of one run, derived only from its events (the same log that drives replay)
function nodeStates(events) {
  const st = {};
  for (const e of events) {
    const p = e.payload || {};
    if (!p.node_id) continue;
    const s = (st[p.node_id] = st[p.node_id] || { status: "pending" });
    if (e.type === "node_started") s.status = "running";
    if (e.type === "node_takeover_waiting") s.status = "waiting";
    if (e.type === "node_finished") Object.assign(s, { status: "done", output: p.output, agent: p.agent });
    if (e.type === "node_failed") Object.assign(s, { status: "failed", error: p.error, agent: p.agent });
    if (e.type === "node_skipped") s.status = "skipped";
  }
  return st;
}

function describe(e) {
  const p = e.payload || {};
  const who = p.user?.name || p.by?.name;
  switch (e.type) {
    case "plan_created": return `Run planned (${(p.plan || []).length} nodes)${who ? ` by ${who}` : ""}`;
    case "node_claimed": return `${who} took over ${p.node_id}`;
    case "node_released": return `${who} released ${p.node_id}`;
    case "node_submitted": return `${who} submitted ${p.node_id}`;
    case "node_takeover_waiting": return `${p.node_id} is waiting for ${who}`;
    case "node_takeover_released": return `${p.node_id} handed back to the agents`;
    case "node_started": return `${p.node_id} (${p.skill}) started`;
    case "node_finished": return `${p.node_id} finished by ${p.agent}`;
    case "node_failed": return `${p.node_id} failed: ${String(p.error).slice(0, 90)}`;
    case "node_skipped": return `${p.node_id} skipped`;
    case "conflict_found": return `Conflict: ${p.label}`;
    case "conflict_resolved": return `Conflict ${p.label} resolved as ${p.value}`;
    case "run_finished": return `Run finished: ${p.status}`;
    default: return e.type;
  }
}

function AuthPanel({ api, onAuth }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", name: "" });
  const [error, setError] = useState(null);
  const submit = async (ev) => {
    ev.preventDefault();
    try {
      const res = await axios.post(`${api}/auth/${mode}`, form);
      onAuth(res.data);
    } catch (e) {
      setError(errText(e));
    }
  };
  return (
    <form style={{ ...card, maxWidth: 420 }} onSubmit={submit}>
      <h3 style={{ marginTop: 0 }}>{mode === "login" ? "Log in" : "Create an account"} to use live sessions</h3>
      {mode === "register" && (
        <input style={{ ...input, width: "100%", marginBottom: 8 }} placeholder="Name"
               value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
      )}
      <input style={{ ...input, width: "100%", marginBottom: 8 }} placeholder="Email" autoComplete="username"
             value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
      <input style={{ ...input, width: "100%", marginBottom: 8 }} placeholder="Password (8+ characters)" type="password"
             autoComplete={mode === "login" ? "current-password" : "new-password"}
             value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
      {error && <div style={{ color: "#ff9187", marginBottom: 8 }}>{error}</div>}
      <button style={button} type="submit">{mode === "login" ? "Log in" : "Register"}</button>{" "}
      <button style={ghost} type="button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}>
        {mode === "login" ? "New here? Register" : "Have an account? Log in"}
      </button>
    </form>
  );
}

export default function LiveSessions({ backendUrl }) {
  const api = backendUrl;
  const [authState, setAuthState] = useState(() => JSON.parse(sessionStorage.getItem(AUTH_KEY) || "null"));
  const [sessions, setSessions] = useState([]);
  const [view, setView] = useState(null);
  const [online, setOnline] = useState([]);
  const [events, setEvents] = useState({});
  const [selectedRun, setSelectedRun] = useState(null);
  const [newTitle, setNewTitle] = useState("");
  const [newMode, setNewMode] = useState("collaborative");
  const [joinToken, setJoinToken] = useState("");
  const [query, setQuery] = useState("Write a short report on Tesla revenue in 2023 with a chart");
  const [drafts, setDrafts] = useState({});
  const [digest, setDigest] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const wsRef = useRef(null);

  const headers = useMemo(() => (authState ? { Authorization: `Bearer ${authState.token}` } : {}), [authState]);
  const me = authState?.user;

  const logout = () => {
    sessionStorage.removeItem(AUTH_KEY);
    wsRef.current?.close();
    setAuthState(null);
    setView(null);
  };

  const call = useCallback(async (label, fn) => {
    setBusy(label);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      if (e.response?.status === 401) logout();
      setError(errText(e));
      return null;
    } finally {
      setBusy(null);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const loadSessions = useCallback(async () => {
    const res = await call("sessions", () => axios.get(`${api}/sessions`, { headers }));
    if (res) setSessions(res.data);
  }, [api, headers, call]);

  const refreshView = useCallback(async (sid) => {
    const res = await call("view", () => axios.get(`${api}/sessions/${sid}`, { headers }));
    if (res) setView(res.data);
  }, [api, headers, call]);

  const loadRunEvents = useCallback(async (runId) => {
    const res = await call("run", () => axios.get(`${api}/runs/${runId}`));
    if (res) {
      const stored = res.data.events.map((e) => ({ ...e, run_id: runId }));
      setEvents((prev) => ({ ...prev, [runId]: stored }));
    }
  }, [api, call]);

  const onAuth = (data) => {
    sessionStorage.setItem(AUTH_KEY, JSON.stringify(data));
    setAuthState(data);
  };

  // invite links: ?join=<token>
  useEffect(() => {
    if (!authState) return;
    const token = new URLSearchParams(window.location.search).get("join");
    loadSessions();
    if (token) {
      window.history.replaceState({}, "", window.location.pathname);
      call("join", () => axios.post(`${api}/sessions/join`, { token }, { headers })).then((res) => {
        if (res) { setView(res.data); loadSessions(); }
      });
    }
  }, [authState]); // eslint-disable-line react-hooks/exhaustive-deps

  // live connection for the open session
  const sessionId = view?.id;
  useEffect(() => {
    if (!sessionId || !authState) return undefined;
    const ws = new WebSocket(`${api.replace(/^http/, "ws")}/ws/${sessionId}?token=${authState.token}`);
    wsRef.current = ws;
    ws.onmessage = (m) => {
      const msg = JSON.parse(m.data);
      if (msg.type === "presence") setOnline(msg.users);
      if (msg.type === "error") setError(msg.detail);
      if (msg.type === "members" || msg.type === "mode") refreshView(sessionId);
      if (msg.type === "event") {
        const e = msg.event;
        setEvents((prev) => {
          const list = prev[e.run_id] || [];
          if (list.some((x) => x.seq === e.seq)) return prev;
          return { ...prev, [e.run_id]: [...list, e] };
        });
        if (["plan_created", "node_claimed", "node_released", "node_submitted", "run_finished"].includes(e.type)) {
          refreshView(sessionId);
        }
        if (e.type === "plan_created") setSelectedRun(e.run_id);
      }
    };
    return () => ws.close();
  }, [sessionId, authState, api, refreshView]);

  if (!authState) return <AuthPanel api={api} onAuth={onAuth} />;

  const role = view?.role;
  const canEdit = role === "owner" || role === "editor";
  const run = view?.runs.find((r) => r.id === selectedRun);
  const runEvents = (run && events[run.id]) || [];
  const states = nodeStates(runEvents);
  const locks = (run && view?.takeovers?.[run.id]) || {};
  const inviteUrl = (t) => `${window.location.origin}${window.location.pathname}?join=${t}`;

  const openSession = async (sid) => {
    setDigest(null);
    setSelectedRun(null);
    await refreshView(sid);
  };
  const createSession = async () => {
    const res = await call("create", () => axios.post(`${api}/sessions`, { title: newTitle || "Untitled session", mode: newMode }, { headers }));
    if (res) { setView(res.data); setNewTitle(""); loadSessions(); }
  };
  const joinSession = async () => {
    const token = joinToken.includes("join=") ? joinToken.split("join=")[1] : joinToken.trim();
    const res = await call("join", () => axios.post(`${api}/sessions/join`, { token }, { headers }));
    if (res) { setView(res.data); setJoinToken(""); loadSessions(); }
  };
  const upgrade = () => call("mode", () => axios.post(`${api}/sessions/${view.id}/mode`, { mode: "collaborative" }, { headers }))
    .then((res) => res && setView(res.data));
  const planRun = async () => {
    const res = await call("plan", () => axios.post(`${api}/sessions/${view.id}/runs`, { query }, { headers, timeout: 90000 }));
    if (res) { setSelectedRun(res.data.run_id); await refreshView(view.id); loadRunEvents(res.data.run_id); }
  };
  const startRun = () => call("start", () => axios.post(`${api}/sessions/${view.id}/runs/${run.id}/start`, {}, { headers }))
    .then(() => refreshView(view.id));
  const nodeAction = (nodeId, action, body = {}) =>
    call(`${action}-${nodeId}`, () => axios.post(`${api}/sessions/${view.id}/runs/${run.id}/nodes/${nodeId}/${action}`, body, { headers }))
      .then(() => refreshView(view.id));
  const selectRun = (rid) => { setSelectedRun(rid); loadRunEvents(rid); };
  const loadDigest = async () => {
    const res = await call("digest", () => axios.get(`${api}/sessions/${view.id}/digest`, { headers, timeout: 60000 }));
    if (res) setDigest(res.data);
  };
  const markRead = async () => {
    if (digest?.latest_event_id) await call("seen", () => axios.post(`${api}/sessions/${view.id}/seen`, { event_id: digest.latest_event_id }, { headers }));
    setDigest(null);
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 16, color: TEXT }}>
      {/* ---------- left: sessions ---------- */}
      <div>
        <div style={card}>
          <div style={{ fontSize: 13, opacity: 0.8 }}>Logged in as</div>
          <b>{me.name}</b> <span style={{ opacity: 0.6, fontSize: 12 }}>{me.email}</span>
          <div><button style={{ ...ghost, marginTop: 8 }} onClick={logout}>Log out</button></div>
        </div>
        <div style={card}>
          <b>Your sessions</b>
          {sessions.length === 0 && <div style={{ opacity: 0.6, fontSize: 13 }}>None yet</div>}
          {sessions.map((s) => (
            <div key={s.id} onClick={() => openSession(s.id)}
                 style={{ cursor: "pointer", padding: "6px 0", borderBottom: `1px solid ${LINE}`, color: s.id === view?.id ? GOLD : TEXT }}>
              {s.title} <span style={{ fontSize: 11, opacity: 0.7 }}>· {s.role} · {s.mode}</span>
            </div>
          ))}
          <input style={{ ...input, width: "100%", marginTop: 10 }} placeholder="New session title"
                 value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
          <select style={{ ...input, width: "100%", marginTop: 6 }} value={newMode} onChange={(e) => setNewMode(e.target.value)}>
            <option value="collaborative">collaborative (others can join)</option>
            <option value="isolated">isolated (only you)</option>
          </select>
          <button style={{ ...button, marginTop: 6 }} onClick={createSession}>Create session</button>
          <input style={{ ...input, width: "100%", marginTop: 14 }} placeholder="Paste an invite link or code"
                 value={joinToken} onChange={(e) => setJoinToken(e.target.value)} />
          <button style={{ ...ghost, marginTop: 6 }} onClick={joinSession} disabled={!joinToken}>Join</button>
        </div>
      </div>

      {/* ---------- right: open session ---------- */}
      <div>
        {error && <div style={{ ...card, borderColor: "#ff9187", color: "#ff9187" }}>{error}</div>}
        {!view && <div style={card}>Create a session or open one on the left. Invite others with the links shown inside a session.</div>}
        {view && (
          <>
            <div style={card}>
              <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                <div>
                  <h3 style={{ margin: 0 }}>{view.title}</h3>
                  <div style={{ fontSize: 13, opacity: 0.8 }}>Mode: <b>{view.mode}</b> · your role: <b>{role}</b></div>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                  <button style={ghost} onClick={loadDigest} disabled={busy === "digest"}>
                    {busy === "digest" ? "Summarising…" : "What did I miss?"}
                  </button>
                  {role === "owner" && view.mode === "isolated" && (
                    <button style={button} onClick={upgrade}>Open for collaboration</button>
                  )}
                </div>
              </div>
              <div style={{ marginTop: 10, fontSize: 13 }}>
                Online now:{" "}
                {online.map((u) => (
                  <span key={u.id} style={{ border: `1px solid ${LINE}`, borderRadius: 12, padding: "2px 8px", marginRight: 6 }}>
                    ● {u.name} <span style={{ opacity: 0.6 }}>({u.role})</span>
                  </span>
                ))}
              </div>
              <div style={{ marginTop: 6, fontSize: 12, opacity: 0.75 }}>
                Members: {view.members.map((m) => `${m.name} (${m.role})`).join(", ")}
              </div>
              {view.invites && view.mode === "collaborative" && (
                <div style={{ marginTop: 10, fontSize: 12 }}>
                  {["editor", "viewer"].map((r) => (
                    <div key={r} style={{ marginBottom: 4 }}>
                      Invite as {r}:{" "}
                      <code style={{ userSelect: "all" }}>{inviteUrl(view.invites[r])}</code>{" "}
                      <button style={{ ...ghost, padding: "2px 8px" }}
                              onClick={() => navigator.clipboard.writeText(inviteUrl(view.invites[r]))}>Copy</button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {digest && (
              <div style={{ ...card, borderColor: "#7fb2ff" }}>
                <b>Since you last looked</b> <span style={{ fontSize: 12, opacity: 0.7 }}>({digest.event_count} events · summary by {digest.summary_by})</span>
                <p style={{ margin: "8px 0" }}>{digest.summary}</p>
                <ul style={{ fontSize: 13, opacity: 0.85, maxHeight: 180, overflowY: "auto" }}>
                  {digest.lines.map((l, i) => <li key={i}>{l}</li>)}
                </ul>
                <button style={button} onClick={markRead}>Mark as read</button>
              </div>
            )}

            <div style={card}>
              <b>Runs in this session</b>
              {canEdit && (
                <div style={{ display: "flex", gap: 8, margin: "10px 0" }}>
                  <input style={{ ...input, flex: 1 }} value={query} onChange={(e) => setQuery(e.target.value)} />
                  <button style={button} onClick={planRun} disabled={busy === "plan" || !query.trim()}>
                    {busy === "plan" ? "Planning…" : "Plan run"}
                  </button>
                </div>
              )}
              {view.runs.map((r) => (
                <div key={r.id} onClick={() => selectRun(r.id)}
                     style={{ cursor: "pointer", padding: "5px 0", color: r.id === selectedRun ? GOLD : TEXT }}>
                  <b>{r.status}</b> · {r.query}
                </div>
              ))}
            </div>

            {run && (
              <div style={card}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <b>{run.query}</b>
                  {canEdit && run.status === "planned" && (
                    <button style={button} onClick={startRun} disabled={busy === "start"}>Start run</button>
                  )}
                </div>
                <div style={{ fontSize: 12, opacity: 0.75, margin: "4px 0 10px" }}>
                  {run.status === "planned"
                    ? "Planned. Editors can take over a node now; when the run reaches it, it waits for that person's text instead of an agent."
                    : `Status: ${run.status}`}
                </div>
                {run.plan.map((n) => {
                  const st = states[n.id] || { status: "pending" };
                  const lock = locks[n.id];
                  const mine = lock && lock.user.id === me.id;
                  return (
                    <div key={n.id} style={{ border: `1px solid ${LINE}`, borderLeft: `4px solid ${STATUS_COLORS[st.status]}`, borderRadius: 8, padding: 10, marginBottom: 8 }}>
                      <b>{n.id}</b> · {n.agent}{" "}
                      <span style={{ color: STATUS_COLORS[st.status] }}>{st.status === "waiting" ? `waiting for ${lock?.user.name || "a person"}` : st.status}</span>
                      {st.agent && <span style={{ opacity: 0.7 }}> · by {st.agent}</span>}
                      <span style={{ opacity: 0.6 }}> · depends on: {n.depends_on.join(", ") || "none"}</span>
                      {lock && !["done", "skipped", "failed"].includes(st.status) && <span style={{ color: "#7fb2ff" }}> · 🔒 {lock.user.name}</span>}
                      {canEdit && run.status === "planned" && (
                        <span style={{ marginLeft: 8 }}>
                          {!lock && <button style={{ ...ghost, padding: "2px 8px" }} onClick={() => nodeAction(n.id, "claim")}>Take over</button>}
                          {mine && <button style={{ ...ghost, padding: "2px 8px" }} onClick={() => nodeAction(n.id, "release")}>Release</button>}
                        </span>
                      )}
                      {mine && st.status === "waiting" && (
                        <div style={{ marginTop: 8 }}>
                          <div style={{ fontSize: 12, opacity: 0.8 }}>
                            Your turn. Upstream outputs are shown below; write this node's output (cite sources as [1] where relevant).
                          </div>
                          {n.depends_on.map((d) => states[d]?.output && (
                            <details key={d} style={{ fontSize: 12, margin: "4px 0" }}>
                              <summary style={{ cursor: "pointer", color: GOLD }}>Show {d} output</summary>
                              <NodeOutput text={states[d].output} />
                            </details>
                          ))}
                          <textarea style={{ ...input, width: "100%", minHeight: 120, marginTop: 6 }}
                                    value={drafts[n.id] || ""} onChange={(e) => setDrafts({ ...drafts, [n.id]: e.target.value })} />
                          <button style={{ ...button, marginTop: 6 }} disabled={!(drafts[n.id] || "").trim()}
                                  onClick={() => nodeAction(n.id, "submit", { output: drafts[n.id] })}>Submit my output</button>{" "}
                          <button style={ghost} onClick={() => nodeAction(n.id, "release")}>Hand back to agents</button>
                        </div>
                      )}
                      {st.output && (
                        <details style={{ marginTop: 6 }}>
                          <summary style={{ cursor: "pointer", color: GOLD }}>Show output</summary>
                          <div style={{ maxHeight: 420, overflowY: "auto", fontSize: 13 }}><NodeOutput text={st.output} /></div>
                        </details>
                      )}
                      {st.error && <div style={{ color: "#ff9187", fontSize: 12 }}>{st.error}</div>}
                    </div>
                  );
                })}
                <div style={{ marginTop: 10 }}>
                  <b style={{ fontSize: 13 }}>Live activity</b>
                  <div style={{ fontSize: 12, opacity: 0.85, maxHeight: 200, overflowY: "auto", marginTop: 4 }}>
                    {runEvents.filter((e) => !QUIET.has(e.type)).slice().reverse().map((e) => (
                      <div key={`${e.seq}`}>#{e.seq} {describe(e)}</div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
