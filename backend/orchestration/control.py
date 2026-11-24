"""Mid-task control of single nodes (synopsis §6.1): pause, resume, redirect, reassign.

A person can act on one node while the rest of the graph keeps running:
  pause     the node will not start; if its agent call is running, that call is cancelled cleanly
  resume    the node may run again (optionally with a new instruction and/or a different agent)
  redirect  restart the node now with an added instruction
  reassign  restart the node now on another agent of the same skill
An interrupted call is not a failure: no attempt is used up and no reputation is changed.
"""
import asyncio


class ControlError(ValueError):
    pass


class Interrupted(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class NodeState:
    def __init__(self):
        self.may_run = asyncio.Event()
        self.may_run.set()
        self.call: asyncio.Task | None = None
        self.reason: str | None = None
        self.instruction: str | None = None
        self.agent: str | None = None
        self.done = False


class RunControl:
    def __init__(self):
        self.nodes: dict[str, NodeState] = {}

    def _node(self, node_id: str) -> NodeState:
        return self.nodes.setdefault(node_id, NodeState())

    def _live(self, node_id: str) -> NodeState:
        node = self._node(node_id)
        if node.done:
            raise ControlError(f"node {node_id} has already finished")
        return node

    def _interrupt(self, node: NodeState, reason: str):
        if node.call is not None and not node.call.done():
            node.reason = reason
            node.call.cancel()

    # ----- actions from people -----
    def pause(self, node_id: str):
        node = self._live(node_id)
        node.may_run.clear()
        self._interrupt(node, "paused")

    def resume(self, node_id: str, instruction: str | None = None, agent: str | None = None):
        node = self._live(node_id)
        if instruction:
            node.instruction = instruction
        if agent:
            node.agent = agent
        node.may_run.set()

    def redirect(self, node_id: str, instruction: str):
        if not (instruction or "").strip():
            raise ControlError("instruction is empty")
        node = self._live(node_id)
        node.instruction = instruction
        node.may_run.set()
        self._interrupt(node, "redirected")

    def reassign(self, node_id: str, agent: str):
        node = self._live(node_id)
        node.agent = agent
        node.may_run.set()
        self._interrupt(node, "reassigned")

    # ----- executor side -----
    def is_paused(self, node_id: str) -> bool:
        return not self._node(node_id).may_run.is_set()

    async def gate(self, node_id: str):
        await self._node(node_id).may_run.wait()

    def take_directive(self, node_id: str) -> dict:
        node = self._node(node_id)
        directive = {"instruction": node.instruction, "agent": node.agent}
        node.instruction = node.agent = None
        return directive

    async def run(self, node_id: str, coro):
        node = self._node(node_id)
        node.reason = None
        node.call = asyncio.ensure_future(coro)
        try:
            return await node.call
        except asyncio.CancelledError:
            if node.reason:   # cancelled by a person, not by the run itself
                reason, node.reason = node.reason, None
                raise Interrupted(reason)
            raise
        finally:
            if not node.call.done():
                node.call.cancel()
            node.call = None

    def finished(self, node_id: str):
        self._node(node_id).done = True

    def snapshot(self) -> dict:
        return {nid: {"paused": not n.may_run.is_set(), "done": n.done} for nid, n in self.nodes.items()}
