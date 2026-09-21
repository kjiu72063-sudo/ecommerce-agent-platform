"""B2 状态与持久化 - FastAPI 路由"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from runtime import (
    EventStore,
    InMemoryEventRepository,
    InMemoryTaskRepository,
    TaskFilter,
    TaskService,
)

app = FastAPI(title="B2 状态与持久化", version="0.1.0")


def get_task_service() -> TaskService:
    if not hasattr(get_task_service, "_instance"):
        task_repo = InMemoryTaskRepository()
        event_repo = InMemoryEventRepository()
        get_task_service._instance = TaskService(task_repo, event_repo)
    return get_task_service._instance


def get_event_store() -> EventStore:
    if not hasattr(get_event_store, "_instance"):
        event_repo = InMemoryEventRepository()
        get_event_store._instance = EventStore(event_repo)
    return get_event_store._instance


class ApiResponse(BaseModel):
    status: str = "success"
    data: dict | None = None
    error: Optional[str] = None


class CreateTaskRequest(BaseModel):
    payload: dict = Field(..., description="任务对象")
    actor_type: str = Field("user")
    actor_id: str = Field("system")


class TaskActionRequest(BaseModel):
    actor_type: str = Field("user")
    actor_id: str = Field("system")
    reason: Optional[str] = None


# ============================================================
# Task API
# ============================================================


@app.post("/api/v2/tasks", response_model=ApiResponse)
async def create_task(request: CreateTaskRequest):
    """创建任务"""
    try:
        service = get_task_service()
        result = await service.create_task(
            request.payload, {"actor_type": request.actor_type, "actor_id": request.actor_id}
        )
        return ApiResponse(status="success", data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/v2/tasks/{task_id}", response_model=ApiResponse)
async def get_task(task_id: str):
    """获取任务详情"""
    service = get_task_service()
    result = await service.get_task(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return ApiResponse(status="success", data=result)


@app.get("/api/v2/tasks", response_model=ApiResponse)
async def list_tasks(
    phase: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """查询任务列表"""
    service = get_task_service()
    filter = TaskFilter(phase=phase, domain=domain, tenant_id=tenant_id)
    results = await service.list_tasks(filter, limit)
    return ApiResponse(status="success", data={"items": results, "total": len(results)})


@app.post("/api/v2/tasks/{task_id}/validate", response_model=ApiResponse)
async def validate_task(task_id: str, request: TaskActionRequest):
    """验证任务"""
    try:
        service = get_task_service()
        result = await service.validate_task(
            task_id, {"actor_type": request.actor_type, "actor_id": request.actor_id}
        )
        return ApiResponse(status="success", data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v2/tasks/{task_id}/queue", response_model=ApiResponse)
async def queue_task(task_id: str):
    """将任务加入队列"""
    try:
        service = get_task_service()
        result = await service.queue_task(task_id)
        return ApiResponse(status="success", data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v2/tasks/{task_id}/start", response_model=ApiResponse)
async def start_task(task_id: str):
    """开始执行任务"""
    try:
        service = get_task_service()
        result = await service.start_task(task_id)
        return ApiResponse(status="success", data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v2/tasks/{task_id}/complete", response_model=ApiResponse)
async def complete_task(task_id: str, artifact_id: str | None = None):
    """完成任务"""
    try:
        service = get_task_service()
        result = await service.complete_task(task_id, artifact_id)
        return ApiResponse(status="success", data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v2/tasks/{task_id}/fail", response_model=ApiResponse)
async def fail_task(
    task_id: str, error_code: str = "INTERNAL_ERROR", error_message: str = "Unknown error"
):
    """任务失败"""
    try:
        service = get_task_service()
        result = await service.fail_task(task_id, error_code, error_message)
        return ApiResponse(status="success", data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v2/tasks/{task_id}/cancel", response_model=ApiResponse)
async def cancel_task(task_id: str, request: TaskActionRequest):
    """取消任务"""
    try:
        service = get_task_service()
        result = await service.cancel_task(task_id, request.reason)
        return ApiResponse(status="success", data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================
# Event API
# ============================================================


@app.get("/api/v2/events/{subject_id}", response_model=ApiResponse)
async def get_events(subject_id: str, after_sequence: int = Query(0)):
    """获取事件流"""
    store = get_event_store()
    events = await store.get_events(subject_id, after_sequence)
    return ApiResponse(status="success", data={"events": events, "total": len(events)})


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "B2-状态与持久化"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
