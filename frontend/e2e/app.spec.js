import { expect, test } from "@playwright/test";
import { conflictRun, metrics, mockBackend, taskRun } from "./mocks.js";

test("a task run shows the DAG, routing, cost and a rendered chart", async ({ page }) => {
  await mockBackend(page, { "POST /tasks/run": taskRun });
  await page.goto("/");
  await expect(page.getByText("Online (:8000)")).toBeVisible();
  await page.getByRole("button", { name: /Assemble Agora & Run/ }).click();

  await expect(page.locator(".agent-node-card")).toHaveCount(2);
  await expect(page.getByText(/research-v1 · quality 1/)).toBeVisible();
  await expect(page.getByText(/3 LLM calls · 1,600 tokens/)).toBeVisible();

  await page.locator(".agent-node-card").filter({ hasText: "[n2]" }).click();
  await expect(page.getByText("Chart: Revenue 2023")).toBeVisible();
  await expect(page.locator(".output-prose svg, .output-prose canvas").first()).toBeVisible();  // Vega rendered
});

test("a conflict is reviewed and the decision is sent to the backend", async ({ page }) => {
  const resolved = structuredClone(conflictRun.conflicts);
  resolved[0].status = "resolved";
  resolved[0].resolution = { choice: 0, value: "$96.77 billion", agreed_with_recommendation: true };
  const calls = await mockBackend(page, {
    "POST /tasks/conflict-demo": conflictRun,
    "POST /runs/run-e2e-2/conflicts/c1/resolve": { conflict: resolved[0], conflicts: resolved, run_status: "complete", fork: null },
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Trigger Conflict Arbitration Demo/ }).click();

  await expect(page.getByText("Tesla revenue (2023)").first()).toBeVisible();
  await expect(page.getByText("Awaiting human review · policy: source authority")).toBeVisible();
  await page.getByRole("button", { name: "Accept $96.77 billion" }).click();

  await expect(page.getByText("✓ Resolved by reviewer: $96.77 billion")).toBeVisible();
  const sent = calls.find((c) => c.key === "POST /runs/run-e2e-2/conflicts/c1/resolve");
  expect(sent.body).toEqual({ choice: 0, rerun: false });
});

test("the observability dashboard shows stored metrics", async ({ page }) => {
  await mockBackend(page, { "GET /metrics/overview": metrics });
  await page.goto("/");
  await page.getByText("Observability", { exact: true }).click();

  await expect(page.getByText("83%")).toBeVisible();
  await expect(page.getByText("✓ intact")).toBeVisible();
  await expect(page.getByRole("cell", { name: /research-v1/ })).toBeVisible();
  await expect(page.getByText(/2 structured conflicts: 2 resolved by a reviewer/)).toBeVisible();
});

test("live sessions: register, create a session and see the invite links", async ({ page }) => {
  const user = { id: "u1", name: "Alice", email: "alice@example.test" };
  const view = { id: "s1", title: "Demo session", mode: "collaborative", role: "owner", members: [{ user_id: "u1", name: "Alice", role: "owner" }],
                 online: [], runs: [], takeovers: {}, invites: { editor: "edit-token", viewer: "view-token" } };
  await page.routeWebSocket(/ws:\/\/127\.0\.0\.1:8000\/ws\/.*/, (ws) => {
    ws.send(JSON.stringify({ type: "presence", users: [{ ...user, role: "owner" }] }));
  });
  const calls = await mockBackend(page, {
    "POST /auth/register": { token: "t", user }, "GET /sessions": [], "POST /sessions": view, "GET /sessions/s1": view,
  });
  await page.goto("/");
  await page.getByText("Live Sessions", { exact: true }).click();
  await page.getByRole("button", { name: "New here? Register" }).click();
  await page.getByPlaceholder("Name").fill("Alice");
  await page.getByPlaceholder("Email").fill("alice@example.test");
  await page.getByPlaceholder("Password (8+ characters)").fill("long-test-password");
  await page.getByRole("button", { name: "Register" }).click();

  await expect(page.getByText("Logged in as")).toBeVisible();
  await page.getByPlaceholder("New session title").fill("Demo session");
  await page.getByRole("button", { name: "Create session" }).click();

  await expect(page.getByText(/join=edit-token/)).toBeVisible();
  await expect(page.getByText(/● Alice/)).toBeVisible();
  expect(calls.find((c) => c.key === "POST /sessions").body).toEqual({ title: "Demo session", mode: "collaborative" });
});
