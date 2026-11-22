class PlanError(ValueError):
    """Raised when the planner returns an invalid task graph."""


def validate_plan(plan, allowed_agents):
    if not isinstance(plan, list) or not plan:
        raise PlanError("Plan must be a non-empty list of nodes")

    ids = set()
    for node in plan:
        if not isinstance(node, dict) or not {"id", "agent", "depends_on"} <= node.keys():
            raise PlanError(f"Node is missing id/agent/depends_on: {node}")
        if node["id"] in ids:
            raise PlanError(f"Duplicate node id: {node['id']}")
        ids.add(node["id"])
        if node["agent"] not in allowed_agents:
            raise PlanError(f"Unknown agent '{node['agent']}'")
        if not isinstance(node["depends_on"], list):
            raise PlanError(f"depends_on must be a list in node {node['id']}")

    for node in plan:
        for dep in node["depends_on"]:
            if dep == node["id"]:
                raise PlanError(f"Node {node['id']} depends on itself")
            if dep not in ids:
                raise PlanError(f"Node {node['id']} depends on unknown node '{dep}'")

    # Cycle check (Kahn's algorithm)
    indegree = {n["id"]: len(n["depends_on"]) for n in plan}
    queue = [i for i, d in indegree.items() if d == 0]
    seen = 0
    while queue:
        current = queue.pop()
        seen += 1
        for n in plan:
            if current in n["depends_on"]:
                indegree[n["id"]] -= 1
                if indegree[n["id"]] == 0:
                    queue.append(n["id"])
    if seen != len(plan):
        raise PlanError("Plan contains a dependency cycle")

    return plan