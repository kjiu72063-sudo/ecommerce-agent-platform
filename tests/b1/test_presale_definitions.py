import asyncio
from datetime import datetime, timezone

import pytest

from presale.contracts import ProductQuestion
from presale.definitions import (
    B1DefinitionSource,
    DefinitionResolutionError,
    FrozenConfiguration,
    StaticDefinitionSource,
)
from presale.runner import PresaleQaRunner
from presale.knowledge import KnowledgeSource

TENANT = "tenant-demo"


def _def(kind, object_id, version="1.0.0", phase="active", tenant_id="tenant-demo"):
    return {
        "api_version": "agent-platform/v1alpha1",
        "kind": kind,
        "metadata": {
            "id": object_id,
            "version": version,
            "content_digest": "sha256:" + "a" * 64,
            "scope": {"type": "tenant", "tenant_id": tenant_id},
        },
        "spec": {},
        "status": {"phase": phase, "observed_revision": 1},
    }


class StubRepo:
    def __init__(self, objects):
        self._objects = {obj["metadata"]["id"]: obj for obj in objects}

    async def get_by_id(self, object_id):
        return self._objects.get(object_id)


def _stub_source(objects_by_names):
    agent_id = objects_by_names["agent"]["metadata"]["id"]
    prompt_id = objects_by_names["prompt"]["metadata"]["id"]
    policy_id = objects_by_names["policy"]["metadata"]["id"]
    repo = StubRepo([objects_by_names["agent"], objects_by_names["prompt"], objects_by_names["policy"]])
    return B1DefinitionSource(
        repo,
        agent_spec_id=agent_id,
        prompt_package_id=prompt_id,
        context_policy_id=policy_id,
    )


@pytest.mark.asyncio
async def test_static_source_returns_prototype_constants():
    config = await StaticDefinitionSource().resolve(tenant_id=TENANT)

    assert config.configuration_refs == {"agent_spec": "1.0.0", "prompt_package": "1.0.0"}
    assert config.policy_ref["kind"] == "ContextPolicy"


@pytest.mark.asyncio
async def test_b1_source_freezes_versions_and_digests():
    source = _stub_source(
        {
            "agent": _def("AgentSpec", "agt_01111111-1111-7111-8111-111111111111"),
            "prompt": _def("PromptPackage", "prm_01111111-1111-7111-8111-111111111111", version="2.1.0"),
            "policy": _def("ContextPolicy", "cpo_01111111-1111-7111-8111-111111111111", version="3.0.0"),
        }
    )

    config = await source.resolve(tenant_id=TENANT)

    assert config.configuration_refs["agent_spec"] == "1.0.0"
    assert config.configuration_refs["prompt_package"] == "2.1.0"
    assert config.configuration_refs["context_policy"] == "3.0.0"
    assert config.policy_ref["id"].startswith("cpo_")
    assert config.policy_ref["digest"].startswith("sha256:")


@pytest.mark.asyncio
async def test_b1_source_rejects_definition_out_of_scope():
    source = _stub_source(
        {
            "agent": _def("AgentSpec", "agt_01111111-1111-7111-8111-111111111111", tenant_id="tenant-other"),
            "prompt": _def("PromptPackage", "prm_01111111-1111-7111-8111-111111111111"),
            "policy": _def("ContextPolicy", "cpo_01111111-1111-7111-8111-111111111111"),
        }
    )

    with pytest.raises(DefinitionResolutionError, match="DEFINITION_OUT_OF_SCOPE"):
        await source.resolve(tenant_id=TENANT)


@pytest.mark.asyncio
async def test_b1_source_rejects_non_active_and_missing():
    non_active = _stub_source(
        {
            "agent": _def("AgentSpec", "agt_01111111-1111-7111-8111-111111111111", phase="draft"),
            "prompt": _def("PromptPackage", "prm_01111111-1111-7111-8111-111111111111"),
            "policy": _def("ContextPolicy", "cpo_01111111-1111-7111-8111-111111111111"),
        }
    )
    with pytest.raises(DefinitionResolutionError, match="DEFINITION_NOT_ACTIVE"):
        await non_active.resolve(tenant_id=TENANT)

    missing = _stub_source(
        {
            "agent": _def("AgentSpec", "agt_01111111-1111-7111-8111-111111111111"),
            "prompt": _def("PromptPackage", "prm_01111111-1111-7111-8111-111111111111"),
            "policy": _def("ContextPolicy", "cpo_01111111-1111-7111-8111-111111111111"),
        }
    )
    missing._ids["prompt_package"] = "prm_00000000-0000-7000-8000-000000000000"
    with pytest.raises(DefinitionResolutionError, match="DEFINITION_NOT_FOUND"):
        await missing.resolve(tenant_id=TENANT)