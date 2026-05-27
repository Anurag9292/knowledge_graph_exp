"""WebSocket endpoint for real-time execution streaming."""

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.agents.base import StreamEvent

router = APIRouter(prefix="/ws", tags=["websocket"])

# Registry of active WebSocket connections keyed by run_id
_ws_clients: dict[str, list[WebSocket]] = {}

# Reference to active engines (shared with experiments.py)
# Import at function level to avoid circular imports


def get_active_engines() -> dict[str, Any]:
    """Get the active engines registry from experiments module."""
    from app.api.experiments import _active_engines
    return _active_engines


async def broadcast_event(run_id: str, event: StreamEvent) -> None:
    """Broadcast a StreamEvent to all WebSocket clients watching a run."""
    clients = _ws_clients.get(run_id, [])
    if not clients:
        return

    message = json.dumps({
        "event_type": event.event_type,
        "node_id": event.node_id,
        "data": event.data,
        "timestamp": event.timestamp,
    })

    disconnected: list[WebSocket] = []
    for ws in clients:
        try:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.send_text(message)
        except Exception:
            disconnected.append(ws)

    # Clean up disconnected clients
    for ws in disconnected:
        clients.remove(ws)


async def _stream_execution(ws: WebSocket, run_id: str) -> None:
    """Stream execution events for an active run to a WebSocket client."""
    engines = get_active_engines()
    engine = engines.get(run_id)

    if not engine:
        await ws.send_text(json.dumps({
            "event_type": "error",
            "node_id": "",
            "data": {"message": f"No active execution found for run '{run_id}'"},
            "timestamp": time.time(),
        }))
        return

    # Stream events from the engine
    # Since the engine is already running in a background task,
    # we poll its state and send updates
    last_node_count = 0
    while run_id in engines:
        engine = engines.get(run_id)
        if not engine:
            break

        # Send status updates based on engine state changes
        current_node_count = len(engine.node_results)
        if current_node_count > last_node_count:
            # New node results available
            for i in range(last_node_count, current_node_count):
                result = engine.node_results[i]
                await ws.send_text(json.dumps({
                    "event_type": "node_complete",
                    "node_id": result.node_id,
                    "data": {
                        "agent_type": result.agent_type,
                        "status": result.status,
                        "tokens_used": result.tokens_used,
                        "duration_ms": result.duration_ms,
                        "error": result.error,
                    },
                    "timestamp": time.time(),
                }))
            last_node_count = current_node_count

        await asyncio.sleep(0.1)

    # Send completion message
    await ws.send_text(json.dumps({
        "event_type": "run_complete",
        "node_id": "",
        "data": {"run_id": run_id},
        "timestamp": time.time(),
    }))


async def _handle_client_message(ws: WebSocket, run_id: str, message: str) -> None:
    """Handle incoming messages from WebSocket clients."""
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        await ws.send_text(json.dumps({
            "event_type": "error",
            "node_id": "",
            "data": {"message": "Invalid JSON message"},
            "timestamp": time.time(),
        }))
        return

    action = data.get("action")
    engines = get_active_engines()
    engine = engines.get(run_id)

    if not engine:
        await ws.send_text(json.dumps({
            "event_type": "error",
            "node_id": "",
            "data": {"message": f"No active execution for run '{run_id}'"},
            "timestamp": time.time(),
        }))
        return

    if action == "pause":
        engine.pause()
        await ws.send_text(json.dumps({
            "event_type": "execution_paused",
            "node_id": "",
            "data": {"run_id": run_id},
            "timestamp": time.time(),
        }))

    elif action == "resume":
        engine.resume()
        await ws.send_text(json.dumps({
            "event_type": "execution_resumed",
            "node_id": "",
            "data": {"run_id": run_id},
            "timestamp": time.time(),
        }))

    elif action == "cancel":
        engine.cancel()
        await ws.send_text(json.dumps({
            "event_type": "execution_cancelled",
            "node_id": "",
            "data": {"run_id": run_id},
            "timestamp": time.time(),
        }))

    elif action == "step":
        # Step mode: execute one node at a time
        # This requires the engine to be paused first
        if not engine.is_paused:
            await ws.send_text(json.dumps({
                "event_type": "error",
                "node_id": "",
                "data": {"message": "Engine must be paused to use step mode. Send {\"action\": \"pause\"} first."},
                "timestamp": time.time(),
            }))
            return

        # Execute a single step
        async for event in engine.execute_step():
            await ws.send_text(json.dumps({
                "event_type": event.event_type,
                "node_id": event.node_id,
                "data": event.data,
                "timestamp": event.timestamp,
            }))

    else:
        await ws.send_text(json.dumps({
            "event_type": "error",
            "node_id": "",
            "data": {"message": f"Unknown action: '{action}'. Valid: pause, resume, cancel, step"},
            "timestamp": time.time(),
        }))


# ─── WebSocket Endpoint ───────────────────────────────────────────────────────


@router.websocket("/execution/{run_id}")
async def websocket_execution(ws: WebSocket, run_id: str) -> None:
    """
    WebSocket endpoint for real-time execution streaming.

    On connect: registers the client for the given run_id.
    During execution: streams all StreamEvents as JSON.
    Receives messages: {"action": "pause"|"resume"|"cancel"|"step"}
    """
    await ws.accept()

    # Register client
    if run_id not in _ws_clients:
        _ws_clients[run_id] = []
    _ws_clients[run_id].append(ws)

    # Send connection confirmation
    await ws.send_text(json.dumps({
        "event_type": "connected",
        "node_id": "",
        "data": {
            "run_id": run_id,
            "message": "Connected to execution stream",
        },
        "timestamp": time.time(),
    }))

    # Start streaming task
    stream_task = asyncio.create_task(_stream_execution(ws, run_id))

    try:
        # Listen for client messages
        while True:
            message = await ws.receive_text()
            await _handle_client_message(ws, run_id, message)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        # Cleanup
        stream_task.cancel()
        try:
            await stream_task
        except asyncio.CancelledError:
            pass

        # Unregister client
        clients = _ws_clients.get(run_id, [])
        if ws in clients:
            clients.remove(ws)
        if not clients:
            _ws_clients.pop(run_id, None)
