// Fake backend responses for the browser tests (shapes match the real FastAPI endpoints).
const API = "http://127.0.0.1:8000";

const chartOutput = [
  "**Chart: Revenue 2023** (bar)", "", "All 2 values were checked against the numbers in the research context.", "",
  "```vega-lite",
  JSON.stringify({ $schema: "https://vega.github.io/schema/vega-lite/v5.json", width: "container", height: 200,
    data: { values: [{ category: "Tesla", series: "Revenue", value: 96.77 }, { category: "Ford", series: "Revenue", value: 176.19 }] },
    mark: { type: "bar" }, encoding: { x: { field: "category", type: "nominal" }, y: { field: "value", type: "quantitative" } } }),
  "```",
].join("\n");

const usage = { llm_calls: 3, tokens_in: 1200, tokens_out: 400, tokens_estimated: false, llm_latency_s: 2.1,
                cost_usd: 0.00042, models: ["openai/gpt-oss-120b"] };

export const taskRun = {
  run_id: "run-e2e-1", status: "complete", conflicts: [],
  plan: [{ id: "n1", agent: "research", depends_on: [] }, { id: "n2", agent: "chart", depends_on: ["n1"] }],
  result: { n1: "Tesla's 2023 revenue was $96.77 billion [1].\n\n---\nSources\n[1] SEC EDGAR - https://data.sec.gov/x", n2: chartOutput },
  node_status: { n1: { status: "done", agent: "research-v1", quality: 1.0, usage }, n2: { status: "done", agent: "chart-v2", quality: 1.0, usage } },
  usage: { total: { llm_calls: 6, tokens_in: 2400, tokens_out: 800, cost_usd: 0.00084 } },
};

const side = (value, nodes, agents, authority, reason) => ({
  value, absolute: 0, nodes, agents, authority, authority_reason: reason, trust: 0.9, score: authority,
  claims: [{ node_id: nodes[0], agent: agents[0], quote: `Tesla revenue was ${value}`, sources: [] }],
});

export const conflictRun = {
  run_id: "run-e2e-2", status: "needs_review",
  plan: [{ id: "n1", agent: "research", depends_on: [] }, { id: "n2", agent: "research", depends_on: [] }],
  result: { n1: "Tesla revenue was $96.77 billion [1].", n2: "Tesla revenue was $97.69 billion." },
  node_status: {},
  conflicts: [{ id: "c1", between: ["n1", "n2"], label: "Tesla revenue (2023)", status: "open", recommended: 0,
                policy: "source authority",
                sides: [side("$96.77 billion", ["n1"], ["research-v1"], 1.0, "official regulatory filing (SEC EDGAR)"),
                        side("$97.69 billion", ["n2"], ["research-v2"], 0.2, "no cited source")],
                explanation: "Tesla revenue (2023): node n1 says $96.77 billion; node n2 says $97.69 billion.",
                suggested_resolution: "Use $96.77 billion — official regulatory filing (SEC EDGAR) outranks no cited source." }],
};

export const metrics = {
  window_days: 30, generated_at: "2026-11-24T12:00:00Z", pricing: "notional (free tiers actually charge $0)",
  runs: { total: 12, by_status: { complete: 10, failed: 2 }, success_rate: 0.833, avg_duration_s: 21.4, forks: 2,
          cost_usd: 0.0123, runs_with_cost: 5, per_day: [{ day: "2026-11-23", complete: 4 }, { day: "2026-11-24", complete: 6, failed: 2 }] },
  agents: [{ agent: "research-v1", skill: "research", model: "openai/gpt-oss-120b", nodes: 9, done: 9, failed: 0, success_rate: 1,
             infra_failures: 1, quality_failures: 0, avg_duration_s: 8.4, avg_quality: 1, cost_usd: 0.01, tokens: 9000,
             llm_calls: 30, nodes_with_usage: 5, cost_per_node_usd: 0.002, trust_mean: 0.94, trust_ci95: [0.82, 1], graded_runs: 9 }],
  reputation: { "research-v1": [{ t: "2026-11-24T10:00:00Z", trust: 0.9, quality: 1, source: "output_check" },
                                { t: "2026-11-24T11:00:00Z", trust: 0.94, quality: 1, source: "output_check" }] },
  conflicts: { total: 2, open: 0, resolved: 2, legacy_pairwise: 0, by_policy: { "source authority": 2 },
               reviewer_agreed_with_recommendation: 2, runs_with_conflicts: 2, conflict_rate: 0.167 },
  humans: { takeovers: 1, nodes_written_by_people: 1, conflict_decisions: 2 },
  audit: { ok: true, entries: 120, head: "abc", by_action: {} },
};

const json = (route, body, status = 200) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

/** Route every backend call; `extra` maps "METHOD path" to a body or a function(request) -> body. */
export async function mockBackend(page, extra = {}) {
  const calls = [];
  await page.route(`${API}/**`, async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const key = `${req.method()} ${path}`;
    calls.push({ key, body: req.postDataJSON?.() ?? null });
    if (key in extra) {
      const value = extra[key];
      return json(route, typeof value === "function" ? value(req) : value);
    }
    if (key === "GET /health") return json(route, { status: "ok" });
    return json(route, { detail: `not mocked: ${key}` }, 404);
  });
  return calls;
}
