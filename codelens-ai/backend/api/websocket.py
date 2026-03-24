import asyncio

from fastapi import WebSocket, WebSocketDisconnect

from backend.core.query_pipeline import run_query
from backend.models.database import get_repo


QUERY_TIMEOUT = 60  # seconds


async def query_websocket(websocket: WebSocket, repo_id: str):
    await websocket.accept()

    repo = await asyncio.to_thread(get_repo, repo_id)
    if not repo or repo.status != "ready":
        await websocket.send_json({"type": "error", "message": "Repository not indexed yet"})
        await websocket.close()
        return

    try:
        while True:
            data = await websocket.receive_json()
            query = data.get("query", "").strip()

            if not query:
                await websocket.send_json({"type": "error", "message": "Empty query"})
                continue

            try:
                async with asyncio.timeout(QUERY_TIMEOUT):
                    async for event in _consume_pipeline(query, repo.name, repo.commit_hash, websocket):
                        pass  # _consume_pipeline sends messages directly
            except asyncio.TimeoutError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Query timed out after 60 seconds",
                })
            except Exception as e:
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
            await websocket.close()
        except Exception:
            pass


async def _consume_pipeline(query: str, repo_name: str, commit_hash: str, websocket: WebSocket):
    async for event in run_query(query, repo_name, commit_hash):
        if event["type"] == "thinking":
            step = event["step"]
            await websocket.send_json({
                "type": "thinking",
                "step_type": step.step_type,
                "message": step.display,
            })
        elif event["type"] == "answer_chunk":
            await websocket.send_json({
                "type": "answer_chunk",
                "content": event["content"],
            })
        elif event["type"] == "sources":
            await websocket.send_json({
                "type": "sources",
                "files": event["sources"],
            })
        elif event["type"] == "error":
            await websocket.send_json({
                "type": "error",
                "message": event["message"],
            })
        elif event["type"] == "done":
            await websocket.send_json({"type": "done"})
        yield event
