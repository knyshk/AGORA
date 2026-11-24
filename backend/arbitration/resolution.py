"""Human approval gate: a reviewer picks the correct side of a conflict.

The decision is stored in the run's event log, and it is graded evidence for reputation:
agents on the losing side get quality 0 counted twice (a human-confirmed error is strong
evidence), agents on the winning side get quality 1 once. Optionally the losing node is re-run
(fork from checkpoint) with the approved figure as an instruction.
"""
import copy


class ResolutionError(ValueError):
    pass


LOSER_WEIGHT = 2


def resolve(conflicts: list, cid: str, choice: int, note: str = "") -> tuple:
    conflicts = copy.deepcopy(conflicts or [])
    conflict = next((c for c in conflicts if c.get("id") == cid), None)
    if conflict is None:
        raise ResolutionError(f"conflict '{cid}' not found in this run")
    if conflict.get("status") != "open":
        raise ResolutionError(f"conflict '{cid}' is already {conflict.get('status')}")
    sides = conflict.get("sides") or []
    if not 0 <= choice < len(sides):
        raise ResolutionError(f"choice must be between 0 and {len(sides) - 1}")
    winner = sides[choice]
    losers = [s for i, s in enumerate(sides) if i != choice]
    conflict["status"] = "resolved"
    conflict["resolution"] = {"choice": choice, "value": winner["value"], "note": note[:500],
                              "agreed_with_recommendation": choice == conflict.get("recommended", 0)}
    return conflicts, conflict, winner, losers


def origin_agents(side: dict, plan: list) -> list:
    """Agents of the nodes where a claim ORIGINATES: a node that only repeats a figure from an
    upstream node on the same side is faithfully using its input and is not penalised."""
    deps = {n["id"]: set(n.get("depends_on", [])) for n in plan or []}
    side_nodes = set(side["nodes"])

    def ancestors(node, seen=None):
        seen = seen if seen is not None else set()
        for d in deps.get(node, ()):
            if d not in seen:
                seen.add(d)
                ancestors(d, seen)
        return seen

    by_node = {c["node_id"]: c["agent"] for c in side["claims"]}
    origins = [n for n in side["nodes"] if not (ancestors(n) & side_nodes)]
    return sorted({by_node[n] for n in origins if by_node.get(n)})


def reputation_updates(winner: dict, losers: list, plan: list = None) -> list:
    """(agent, quality, reason) tuples to apply."""
    updates = [(a, 1.0, "won a reviewed conflict") for a in origin_agents(winner, plan)]
    win_agents = set(origin_agents(winner, plan))
    for side in losers:
        for a in origin_agents(side, plan):
            if a in win_agents:
                continue  # same agent on both sides: no net evidence
            updates += [(a, 0.0, "lost a reviewed conflict")] * LOSER_WEIGHT
    return updates


def correction_instruction(conflict: dict, winner: dict, loser: dict) -> str:
    return (f"A reviewer resolved a factual conflict: {conflict['label']} is {winner['value']} "
            f"(source: {winner['authority_reason']}). Use exactly this figure and do not state {loser['value']}.")


def run_status_after(conflicts: list, current: str) -> str:
    if current == "needs_review" and not any(c.get("status") == "open" for c in conflicts):
        return "complete"
    return current
