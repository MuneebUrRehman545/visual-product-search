import asyncio
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set, Union
from starlette.websockets import WebSocket

logger = logging.getLogger(__name__)

# Event Type Constants
EVENT_PLAN_CREATED = "plan_created"
EVENT_STEP_STARTED = "step_started"
EVENT_TOOL_CALL_STARTED = "tool_call_started"
EVENT_TOOL_CALL_RESULT = "tool_call_result"
EVENT_OBSERVATION_MADE = "observation_made"
EVENT_REPLAN_TRIGGERED = "replan_triggered"
EVENT_STEP_COMPLETED = "step_completed"
EVENT_REPORT_READY = "report_ready"
EVENT_RUN_COMPLETED = "run_completed"
EVENT_RUN_FAILED = "run_failed"
EVENT_CATCH_UP = "catch_up"


class EventEmitter:
    """Thread-safe Pub-Sub event emitter for broadcasting live agent execution
    events to WebSocket subscribers across threads and async tasks."""

    def __init__(self):
        self._subscribers: Dict[str, Set[WebSocket]] = {}
        self._loops: Dict[WebSocket, asyncio.AbstractEventLoop] = {}
        self._lock = threading.Lock()

    def subscribe(
        self,
        run_id: Union[str, uuid.UUID],
        connection: WebSocket,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        """Subscribes a WebSocket connection to live events for a specific run_id."""
        key = str(run_id)
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

        with self._lock:
            if key not in self._subscribers:
                self._subscribers[key] = set()
            self._subscribers[key].add(connection)
            if loop:
                self._loops[connection] = loop
        logger.info(f"Subscribed WebSocket to run {key}. Active subscribers for run: {len(self._subscribers[key])}")

    def unsubscribe(self, run_id: Union[str, uuid.UUID], connection: WebSocket) -> None:
        """Unsubscribes a WebSocket connection from a specific run_id."""
        key = str(run_id)
        with self._lock:
            if key in self._subscribers:
                self._subscribers[key].discard(connection)
                if not self._subscribers[key]:
                    del self._subscribers[key]
            self._loops.pop(connection, None)
        logger.info(f"Unsubscribed WebSocket from run {key}.")

    def emit(
        self,
        run_id: Union[str, uuid.UUID],
        event_type: str,
        payload: Dict[str, Any],
    ) -> None:
        """Dispatches an event payload to all currently subscribed connections for run_id."""
        key = str(run_id)
        with self._lock:
            subscribers = list(self._subscribers.get(key, []))

        if not subscribers:
            return

        message = {
            "type": event_type,
            "event": event_type,
            "run_id": key,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }

        for ws in subscribers:
            loop = self._loops.get(ws)
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._send_and_handle(key, ws, message, event_type),
                    loop,
                )
            else:
                try:
                    curr_loop = asyncio.get_event_loop()
                    if curr_loop.is_running():
                        curr_loop.create_task(self._send_and_handle(key, ws, message, event_type))
                except Exception as e:
                    logger.warning(f"Could not dispatch event {event_type} to websocket: {e}")

    async def _send_and_handle(self, run_id: str, ws: WebSocket, message: dict, event_type: str) -> None:
        """Helper coroutine to send JSON and handle connection lifecycle cleanly."""
        try:
            await ws.send_json(message)
            if event_type in (EVENT_RUN_COMPLETED, EVENT_RUN_FAILED):
                # Clean close after terminal run events
                await asyncio.sleep(0.05)
                try:
                    await ws.close(code=1000)
                except Exception:
                    pass
                self.unsubscribe(run_id, ws)
        except Exception as err:
            logger.debug(f"Failed to send event to WebSocket ({err}), unsubscribing.")
            self.unsubscribe(run_id, ws)

    async def close_all(self, run_id: Union[str, uuid.UUID]) -> None:
        """Explicitly closes all active subscriber connections for a run."""
        key = str(run_id)
        with self._lock:
            subscribers = list(self._subscribers.get(key, []))

        for ws in subscribers:
            try:
                await ws.close(code=1000)
            except Exception:
                pass
            self.unsubscribe(key, ws)


# Global singleton instance for the backend
event_emitter = EventEmitter()
