"""V1 run-trace retention service."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from .trace import DispositionState, RetentionPolicy, TraceError

if TYPE_CHECKING:
    from .ports import RunTraceRepository


class RetentionService:
    """Archive expired, completed run traces through a repository.

    The service owns the retention policy (30 days by default) and the rule
    that only COMPLETE, non-archived traces older than the policy are marked
    archived. History is preserved: traces are never physically deleted.
    """

    def __init__(
        self,
        trace_repo: RunTraceRepository,
        retention_policy: RetentionPolicy | None = None,
    ):
        self._repo = trace_repo
        self._retention = retention_policy or RetentionPolicy()

    def retention_policy(self) -> RetentionPolicy:
        return self._retention

    async def archive_expired(self, *, tenant_id: str, now: datetime) -> list[str]:
        """Mark expired, completed traces as archived while keeping their history."""
        if not tenant_id:
            raise TraceError("TENANT_ID_REQUIRED")
        archived: list[str] = []
        for trace in await self._repo.list_by_tenant(tenant_id=tenant_id):
            if trace.disposition_state is not DispositionState.COMPLETE:
                continue
            if trace.archived:
                continue
            created_at = trace.stages[0].occurred_at
            if self._retention.is_expired(created_at, now):
                await self._repo.mark_archived(trace.run_ref, tenant_id=tenant_id)
                archived.append(trace.run_ref)
        return archived
