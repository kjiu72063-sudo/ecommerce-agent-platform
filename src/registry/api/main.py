"""B1 能力注册中心 - FastAPI 路由

提供定义对象的 CRUD、状态迁移和查询 API。
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from registry import DefinitionFilter, RegistryService

# ============================================================
# 请求/响应模型
# ============================================================


class RegisterRequest(BaseModel):
    """注册请求"""

    kind: str = Field(..., description="资源类型，如 agent-spec, skill-manifest")
    payload: dict = Field(..., description="完整的资源对象")
    actor_type: str = Field("user", description="操作者类型")
    actor_id: str = Field("system", description="操作者 ID")


class TransitionRequest(BaseModel):
    """状态迁移请求"""

    target_phase: str = Field(..., description="目标阶段")
    reason: Optional[str] = Field(None, description="迁移原因")
    actor_type: str = Field("user", description="操作者类型")
    actor_id: str = Field("system", description="操作者 ID")


class ApiResponse(BaseModel):
    """统一响应格式"""

    status: str = "success"
    data: dict | None = None
    error: Optional[str] = None


# ============================================================
# 应用初始化
# ============================================================

app = FastAPI(
    title="B1 能力注册中心", description="定义对象的 CRUD、状态迁移和查询 API", version="0.1.0"
)


# 依赖注入：服务实例
def get_service() -> RegistryService:
    """获取服务实例（单例模式，支持测试时替换）"""
    if not hasattr(get_service, "_instance"):
        from registry import InMemoryDefinitionRepository

        repo = InMemoryDefinitionRepository()
        get_service._instance = RegistryService(repo)
    return get_service._instance


def reset_service():
    """重置服务实例（用于测试）"""
    if hasattr(get_service, "_instance"):
        delattr(get_service, "_instance")


# ============================================================
# 注册 API
# ============================================================


@app.post("/api/v1/registry/definitions", response_model=ApiResponse)
async def register_definition(request: RegisterRequest):
    """注册新的定义对象

    示例请求：
    ```json
    {
        "kind": "agent-spec",
        "payload": { ... }
    }
    ```
    """
    try:
        service = get_service()
        result = await service.register_definition(
            kind=request.kind,
            payload=request.payload,
            actor={"actor_type": request.actor_type, "actor_id": request.actor_id},
        )
        return ApiResponse(status="success", data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 查询 API
# ============================================================


@app.get("/api/v1/registry/definitions/{definition_id}", response_model=ApiResponse)
async def get_definition(definition_id: str):
    """获取定义对象详情"""
    try:
        service = get_service()
        result = await service.get_definition(definition_id)
        if not result:
            raise HTTPException(status_code=404, detail="Definition not found")
        return ApiResponse(status="success", data=result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/registry/definitions", response_model=ApiResponse)
async def list_definitions(
    kind: Optional[str] = Query(None, description="资源类型"),
    namespace: Optional[str] = Query(None, description="命名空间"),
    key: Optional[str] = Query(None, description="标识符"),
    phase: Optional[str] = Query(None, description="生命周期阶段"),
    tenant_id: Optional[str] = Query(None, description="租户 ID"),
    limit: int = Query(100, ge=1, le=1000, description="最大返回数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    """查询定义对象列表

    支持按 kind、namespace、key、phase、tenant_id 过滤。
    """
    try:
        service = get_service()
        filter = DefinitionFilter(
            kind=kind, namespace=namespace, key=key, phase=phase, tenant_id=tenant_id
        )
        results = await service.list_definitions(filter, limit, offset)
        total = await service.repo.count_by_filter(filter)
        return ApiResponse(status="success", data={"items": results, "total": total})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 更新 API
# ============================================================


class UpdateRequest(BaseModel):
    """更新请求"""

    payload: dict = Field(..., description="更新后的资源对象")
    actor_type: str = Field("user", description="操作者类型")
    actor_id: str = Field("system", description="操作者 ID")


@app.put("/api/v1/registry/definitions/{definition_id}", response_model=ApiResponse)
async def update_definition(definition_id: str, request: UpdateRequest):
    """更新定义对象

    使用乐观并发控制：需要提供当前 revision。
    更新后会重新计算 content_digest。
    """
    try:
        service = get_service()
        result = await service.update_definition(
            id=definition_id,
            payload=request.payload,
            actor={"actor_type": request.actor_type, "actor_id": request.actor_id},
        )
        return ApiResponse(status="success", data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 状态迁移 API
# ============================================================


@app.post("/api/v1/registry/definitions/{definition_id}/transition", response_model=ApiResponse)
async def transition_definition(definition_id: str, request: TransitionRequest):
    """迁移定义对象状态

    支持的状态迁移：
    - proposed → draft
    - draft → testing
    - testing → awaiting_approval / draft
    - awaiting_approval → approved / draft
    - approved → active
    - active → deprecated / blocked
    - deprecated → archived
    - blocked → active
    """
    try:
        service = get_service()
        result = await service.transition_state(
            id=definition_id,
            target_phase=request.target_phase,
            reason=request.reason,
            actor={"actor_type": request.actor_type, "actor_id": request.actor_id},
        )
        return ApiResponse(status="success", data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 版本历史 API
# ============================================================


@app.get("/api/v1/registry/definitions/{definition_id}/versions", response_model=ApiResponse)
async def get_versions(definition_id: str):
    """获取定义对象的版本历史"""
    try:
        service = get_service()
        versions = await service.repo.get_versions(definition_id)
        return ApiResponse(status="success", data={"versions": versions})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 依赖关系 API
# ============================================================


@app.get("/api/v1/registry/definitions/{definition_id}/dependencies", response_model=ApiResponse)
async def get_dependencies(definition_id: str, version: Optional[str] = None):
    """获取定义对象的依赖关系"""
    try:
        service = get_service()
        # 如果未指定版本，使用最新版本
        if not version:
            obj = await service.get_definition(definition_id)
            if not obj:
                raise HTTPException(status_code=404, detail="Definition not found")
            version = obj["metadata"]["version"]

        assert version is not None
        deps = await service.repo.get_dependencies(definition_id, version)
        return ApiResponse(status="success", data={"dependencies": deps})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 删除 API
# ============================================================


class DeleteRequest(BaseModel):
    """删除请求"""

    actor_type: str = Field("user", description="操作者类型")
    actor_id: str = Field("system", description="操作者 ID")


@app.delete("/api/v1/registry/definitions/{definition_id}", response_model=ApiResponse)
async def delete_definition(definition_id: str, request: DeleteRequest):
    """删除定义对象

    只有 draft 状态的对象可以删除。
    """
    try:
        service = get_service()
        result = await service.delete_definition(
            id=definition_id, actor={"actor_type": request.actor_type, "actor_id": request.actor_id}
        )
        if not result:
            raise HTTPException(status_code=404, detail="Definition not found")
        return ApiResponse(status="success", data={"deleted": True})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 审计日志 API
# ============================================================


@app.get("/api/v1/registry/audit", response_model=ApiResponse)
async def get_audit_logs(
    resource_id: Optional[str] = Query(None, description="资源 ID"),
    actor_id: Optional[str] = Query(None, description="操作者 ID"),
    limit: int = Query(100, ge=1, le=1000, description="最大返回数量"),
):
    """查询审计日志"""
    try:
        service = get_service()
        logs = await service.repo.get_audit_logs(
            resource_id=resource_id, actor_id=actor_id, limit=limit
        )
        return ApiResponse(status="success", data={"logs": logs, "total": len(logs)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 健康检查
# ============================================================


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "service": "B1-能力注册中心"}


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
