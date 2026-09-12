"""Frozen platform-definition lookup for the presale application."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from agent_platform_contracts.policies import canonical_sha256


class DefinitionResolutionError(ValueError):
    """A required versioned platform definition could not be resolved."""


@dataclass(frozen=True)
class FrozenConfiguration:
    """Version/digest snapshot used by one presale run."""

    configuration_refs: dict[str, str]
    policy_ref: dict[str, str]


class DefinitionSource(ABC):
    """Port for resolving active, tenant-scoped platform definitions."""

    @abstractmethod
    async def resolve(self, *, tenant_id: str) -> FrozenConfiguration:
        """Return an immutable run configuration snapshot for a tenant."""


class StaticDefinitionSource(DefinitionSource):
    """Development fallback preserving the V1 prototype constants."""

    async def resolve(self, *, tenant_id: str) -> FrozenConfiguration:
        return FrozenConfiguration(
            configuration_refs={
                "agent_spec": "1.0.0",
                "prompt_package": "1.0.0",
                "context_policy": "1.0.0",
            },
            policy_ref={
                "kind": "ContextPolicy",
                "id": "cpo_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f416",
                "version": "1.0.0",
                "digest": canonical_sha256({"policy": "presale"}),
            },
        )


class B1DefinitionSource(DefinitionSource):
    """Resolve one active definition for each configured selector."""

    def __init__(
        self,
        repository: Any,
        *,
        selectors: dict[str, dict[str, str]] | None = None,
        agent_spec_id: str | None = None,
        prompt_package_id: str | None = None,
        context_policy_id: str | None = None,
    ):
        self._repository = repository
        self._selectors = selectors
        self._ids = {
            "agent_spec": agent_spec_id,
            "prompt_package": prompt_package_id,
            "context_policy": context_policy_id,
        }

    async def resolve(self, *, tenant_id: str) -> FrozenConfiguration:
        definitions: dict[str, dict] = {}
        for name in ("agent_spec", "prompt_package", "context_policy"):
            definition = await self._resolve_one(name, tenant_id)
            definitions[name] = definition

        agent = definitions["agent_spec"]
        prompt = definitions["prompt_package"]
        policy = definitions["context_policy"]
        return FrozenConfiguration(
            configuration_refs={
                "agent_spec": agent["metadata"]["version"],
                "prompt_package": prompt["metadata"]["version"],
                "context_policy": policy["metadata"]["version"],
            },
            policy_ref={
                "kind": "ContextPolicy",
                "id": policy["metadata"]["id"],
                "version": policy["metadata"]["version"],
                "digest": policy["metadata"]["content_digest"],
            },
        )

    async def _resolve_one(self, name: str, tenant_id: str) -> dict:
        selector = self._selectors.get(name) if self._selectors else None
        if selector is not None:
            from registry.repository import DefinitionFilter

            matches = await self._repository.list_by_filter(
                DefinitionFilter(
                    kind=selector["kind"],
                    namespace=selector["namespace"],
                    key=selector["key"],
                    phase="active",
                    tenant_id=tenant_id,
                )
            )
            if not matches:
                raise DefinitionResolutionError(f"DEFINITION_NOT_FOUND:{name}")
            if len(matches) != 1:
                raise DefinitionResolutionError(f"MULTIPLE_ACTIVE:{name}")
            return matches[0]

        object_id = self._ids.get(name)
        if not object_id:
            raise DefinitionResolutionError(f"DEFINITION_SELECTOR_MISSING:{name}")
        definition = await self._repository.get_by_id(object_id)
        if definition is None:
            raise DefinitionResolutionError(f"DEFINITION_NOT_FOUND:{name}")
        self._check_tenant(definition, tenant_id, name)
        if definition.get("status", {}).get("phase") != "active":
            raise DefinitionResolutionError(f"DEFINITION_NOT_ACTIVE:{name}")
        return definition

    @staticmethod
    def _check_tenant(definition: dict, tenant_id: str, name: str) -> None:
        scope = definition.get("metadata", {}).get("scope", {})
        definition_tenant = scope.get("tenant_id")
        if not definition_tenant or definition_tenant != tenant_id:
            raise DefinitionResolutionError(f"DEFINITION_OUT_OF_SCOPE:{name}")


__all__ = [
    "B1DefinitionSource",
    "DefinitionResolutionError",
    "DefinitionSource",
    "FrozenConfiguration",
    "StaticDefinitionSource",
]
