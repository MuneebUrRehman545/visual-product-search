import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set, Union
from starlette.websockets import WebSocket

logger = logging.getLogger(__name__)

# Pipeline Event Type Constants
EVENT_RUN_CREATED = "run_created"
EVENT_STATUS_UPDATED = "status_updated"
EVENT_VISION_STARTED = "vision_started"
EVENT_VISION_COMPLETED = "vision_completed"
EVENT_VISION_FAILED = "vision_failed"
EVENT_RAG_STARTED = "rag_started"
EVENT_RAG_COMPLETED = "rag_completed"
EVENT_RAG_FAILED = "rag_failed"
EVENT_AGENT_STARTED = "agent_started"
EVENT_AGENT_COMPLETED = "agent_completed"
EVENT_AGENT_FAILED = "agent_failed"
EVENT_RUN_COMPLETED = "run_completed"
EVENT_RUN_FAILED = "run_failed"
EVENT_CATCH_UP = "catch_up"


class PipelineEventEmitter:
    """
    Thread-safe Pub-Sub event emitter for broadcasting live pipeline execution
    and module state updates to WebSocket subscribers across tasks and threads.
    Reuses the proven pattern from the Research Agent's event broadcaster.
    """

    def __init__(self):
        self._subscribers: Dict[str, Set[WebSocket]] = {}
        self._loops: Dict[WebSocket, asyncio.AbstractEventLoop] = {}
        self._lock = threading.Lock()

    def subscribe(
        self,
        pipeline_run_id: Union[str, Any],
        connection: WebSocket,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        """Subscribes a WebSocket connection to live events for a specific pipeline_run_id."""
        key = str(pipeline_run_id)
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

        logger.info(f"Subscribed WebSocket to pipeline_run {key}. Active subscribers: {len(self._subscribers[key])}")

    def unsubscribe(self, pipeline_run_id: Union[str, Any], connection: WebSocket) -> None:
        """Unsubscribes a WebSocket connection from a specific pipeline_run_id."""
        key = str(pipeline_run_id)
        with self._lock:
            if key in self._subscribers:
                self._subscribers[key].discard(connection)
                if not self._subscribers[key]:
                    del self._subscribers[key]
            self._loops.pop(connection, None)
        logger.info(f"Unsubscribed WebSocket from pipeline_run {key}.")

    def emit(
        self,
        pipeline_run_id: Union[str, Any],
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        """Dispatches an event payload to all currently subscribed connections for pipeline_run_id."""
        key = str(pipeline_run_id)
        with self._lock:
            subscribers = list(self._subscribers.get(key, []))

        if not subscribers:
            return

        event_body = {
            "type": event_type,
            "event": event_type,
            "pipeline_run_id": key,
            "run_id": key,
            "status": status,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload or {},
        }

        for ws in subscribers:
            loop = self._loops.get(ws)
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._send_and_handle(key, ws, event_body, event_type, status),
                    loop,
                )
            else:
                try:
                    curr_loop = asyncio.get_event_loop()
                    if curr_loop.is_running():
                        curr_loop.create_task(
                            self._send_and_handle(key, ws, event_body, event_type, status)
                        )
                except Exception as e:
                    logger.warning(f"Could not dispatch pipeline event {event_type} to websocket: {e}")

    async def _send_and_handle(
        self,
        pipeline_run_id: str,
        ws: WebSocket,
        message: dict,
        event_type: str,
        status: Optional[str],
    ) -> None:
        """Helper coroutine to send JSON and cleanly handle connection lifecycle."""
        try:
            await ws.send_json(message)
            # If terminal event or terminal status, close connection cleanly
            if event_type in (EVENT_RUN_COMPLETED, EVENT_RUN_FAILED) or status in ("completed", "failed"):
                await asyncio.sleep(0.05)
                try:
                    await ws.close(code=1000)
                except Exception:
                    pass
                self.unsubscribe(pipeline_run_id, ws)
        except Exception as err:
            logger.debug(f"Failed to send pipeline event to WebSocket ({err}), unsubscribing.")
            self.unsubscribe(pipeline_run_id, ws)

    async def close_all(self, pipeline_run_id: Union[str, Any]) -> None:
        """Explicitly closes all active subscriber connections for a pipeline run."""
        key = str(pipeline_run_id)
        with self._lock:
            subscribers = list(self._subscribers.get(key, []))

        for ws in subscribers:
            try:
                await ws.close(code=1000)
            except Exception:
                pass
            self.unsubscribe(key, ws)


# Global singleton instance for Gateway event broadcasting
pipeline_event_emitter = PipelineEventEmitter()
