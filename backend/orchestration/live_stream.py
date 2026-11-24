"""Batches streamed tokens of one node and forwards them, in order, to a live callback.

Partial output is live-only (WebSocket), never stored: the event log keeps state changes, and the final
output of every node is stored by node_finished as before.
"""
import asyncio
import time

INTERVAL_S = 0.15


class LiveStream:
    def __init__(self, node_id: str, callback, interval: float = INTERVAL_S):
        self.node_id, self.callback, self.interval = node_id, callback, interval
        self.buffer, self.call, self.role = [], None, None
        self.last = 0.0
        self._chain = None   # each send waits for the previous one, so messages never reorder

    def __call__(self, event: dict):
        if event.get("start"):
            self._flush()
            self.call, self.role = event["call"], event["role"]
            self._send({"node_id": self.node_id, "call": self.call, "role": self.role, "start": True})
        elif "delta" in event:
            self.buffer.append(event["delta"])
            if time.monotonic() - self.last >= self.interval:
                self._flush()
        elif event.get("end"):
            self._flush()
            self._send({"node_id": self.node_id, "call": event["call"], "role": event["role"], "end": True})

    def _flush(self):
        if self.buffer:
            self._send({"node_id": self.node_id, "call": self.call, "role": self.role, "delta": "".join(self.buffer)})
            self.buffer = []
        self.last = time.monotonic()

    def _send(self, payload: dict):
        previous = self._chain

        async def send():
            if previous is not None:
                await previous
            try:
                await self.callback(payload)
            except Exception as e:
                print(f"[STREAM] send failed: {type(e).__name__}: {e}")
        self._chain = asyncio.get_running_loop().create_task(send())

    async def drain(self):
        self._flush()
        if self._chain is not None:
            await self._chain
