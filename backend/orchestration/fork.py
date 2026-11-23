def descendants(plan: list, node_id: str) -> set:
    """The node itself plus every node that depends on it, directly or indirectly."""
    result = {node_id}
    changed = True
    while changed:
        changed = False
        for n in plan:
            if n["id"] not in result and any(d in result for d in n["depends_on"]):
                result.add(n["id"])
                changed = True
    return result


def reusable_outputs(plan: list, outputs: dict, rerun_node: str) -> dict:
    """Outputs that are still valid after changing `rerun_node`."""
    affected = descendants(plan, rerun_node)
    return {nid: out for nid, out in outputs.items() if nid not in affected}