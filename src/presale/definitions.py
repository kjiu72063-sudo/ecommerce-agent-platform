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
    artifact_ref: dict[str, str]


class DefinitionSource(ABC):
    """Port for resolving active, tenant-scoped platform definitions."""

    @abstractmethod
    async def resolve(self, *, tenant_id: str) -> FrozenConfiguration:
        """Return an immutable run configuration snapshot for a tenant."""


class StaticDefinitionSource(DefinitionSource):
    """Development fallback preserving the V1 prototype constants."""

    async def resolve(self, *, tenant_id: str) -> FrozenConfiguration:
        return FrozenConfiguration(
            configuration_refs={"agent_spec": "1.0.0", "prompt_package": "1.0.0"},
            policy_ref={
                "kind": "ContextPolicy",
                "id": "cpo_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f416",
                "version": "1.0.0",
                "digest": canonical_sha256({"policy": "presale"}),
            },
            artifact_ref={
                "id": "art_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f427",
                "digest": canonical_sha256({"artifact": "context"}),
            },
        )


class B1DefinitionSource(DefinitionSource):
    """Resolve frozen definitions from a B1 DefinitionRepository."""

    def __init__(
        self,
        repository: Any,
        *,
        agent_spec_id: str,
        prompt_package_id: str,
        context_policy_id: str,
        artifact_ref: dict[str, str] | None = None,
    ):
        self._repository = repository
        self._ids = {
            "agent_spec": agent_spec_id,
            "prompt_package": prompt_package_id,
            "context_policy": context_policy_id,
        }
        self._artifact_ref = artifact_ref or {
            "id": "art_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f427",
            "digest": canonical_sha256({"artifact": "context"}),
        }

    async def resolve(self, *, tenant_id: str) -> FrozenConfiguration:
        definitions: dict[str, dict] = {}
        for name, object_id in self._ids.items():
            definition = await self._repository.get_by_id(object_id)
            if definition is None:
                raise DefinitionResolutionError(f"DEFINITION_NOT_FOUND:{name}")
            self._check_tenant(definition, tenant_id, name)
            if definition.get("status", {}).get("phase") != "active":
                raise DefinitionResolutionError(f"DEFINITION_NOT_ACTIVE:{name}")
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
            artifact_ref=dict(self._artifact_ref),
        )

    @staticmethod
    def _check_tenant(definition: dict, tenant_id: str, name: str) -> None:
        scope = definition.get("metadata", {}).get("scope", {})
        definition_tenant = scope.get("tenant_id")
        if definition_tenant and definition_tenant != tenant_id:
            raise DefinitionResolutionError(f"DEFINITION_OUT_OF_SCOPE:{name}")


__all__ = [
    "B1DefinitionSource",
    "DefinitionResolutionError",
    "DefinitionSource",
    "FrozenConfiguration",
    "StaticDefinitionSource",
]
