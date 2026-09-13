import pytest

from presale.definitions import B1DefinitionSource, DefinitionResolutionError


def definition(
    kind,
    object_id,
    key,
    namespace="presale",
    tenant_id="tenant-demo",
    phase="active",
    version="1.0.0",
):
    return {
        "kind": kind,
        "metadata": {
            "id": object_id,
            "key": key,
            "namespace": namespace,
            "version": version,
            "content_digest": "sha256:" + "a" * 64,
            "scope": {"type": "tenant", "tenant_id": tenant_id},
        },
        "status": {"phase": phase},
    }


class SelectorRepo:
    def __init__(self, objects):
        self.objects = objects

    async def list_by_filter(self, filter, limit=100, offset=0):
        return [
            obj
            for obj in self.objects
            if obj["kind"] == filter.kind
            and obj["metadata"]["namespace"] == filter.namespace
            and obj["metadata"]["key"] == filter.key
            and obj["status"]["phase"] == filter.phase
            and obj["metadata"]["scope"].get("tenant_id") == filter.tenant_id
        ]


@pytest.mark.asyncio
async def test_selector_resolves_single_active_definition():
    objects = [
        definition("AgentSpec", "agt_01111111-1111-7111-8111-111111111111", "presale-agent"),
        definition(
            "PromptPackage",
            "prm_01111111-1111-7111-8111-111111111111",
            "presale-prompt",
            version="2.0.0",
        ),
        definition(
            "ContextPolicy",
            "cpo_01111111-1111-7111-8111-111111111111",
            "presale-context",
            version="3.0.0",
        ),
    ]
    source = B1DefinitionSource(
        SelectorRepo(objects),
        selectors={
            "agent_spec": {"kind": "AgentSpec", "namespace": "presale", "key": "presale-agent"},
            "prompt_package": {
                "kind": "PromptPackage",
                "namespace": "presale",
                "key": "presale-prompt",
            },
            "context_policy": {
                "kind": "ContextPolicy",
                "namespace": "presale",
                "key": "presale-context",
            },
        },
    )

    config = await source.resolve(tenant_id="tenant-demo")

    assert config.configuration_refs == {
        "agent_spec": "1.0.0",
        "prompt_package": "2.0.0",
        "context_policy": "3.0.0",
    }


@pytest.mark.asyncio
async def test_selector_rejects_multiple_active_definitions():
    objects = [
        definition("AgentSpec", "agt_01111111-1111-7111-8111-111111111111", "presale-agent"),
        definition(
            "AgentSpec",
            "agt_02222222-2222-7222-8222-222222222222",
            "presale-agent",
            version="2.0.0",
        ),
    ]
    source = B1DefinitionSource(
        SelectorRepo(objects),
        selectors={
            "agent_spec": {"kind": "AgentSpec", "namespace": "presale", "key": "presale-agent"}
        },
    )

    with pytest.raises(DefinitionResolutionError, match="MULTIPLE_ACTIVE"):
        await source.resolve(tenant_id="tenant-demo")


@pytest.mark.asyncio
async def test_selector_defensively_rejects_cross_tenant_definition():
    # Adapter that leaks a foreign-tenant definition despite the requested tenant_id,
    # simulating a compromised/incorrect list_by_filter; selector must still reject it.
    class LeakySelectorRepo(SelectorRepo):
        async def list_by_filter(self, filter, limit=100, offset=0):
            return [
                obj
                for obj in self.objects
                if obj["kind"] == filter.kind
                and obj["metadata"]["namespace"] == filter.namespace
                and obj["metadata"]["key"] == filter.key
                and obj["status"]["phase"] == filter.phase
            ]

    objects = [
        definition(
            "AgentSpec",
            "agt_01111111-1111-7111-8111-111111111111",
            "presale-agent",
            tenant_id="tenant-other",
        ),
        definition(
            "PromptPackage",
            "prm_01111111-1111-7111-8111-111111111111",
            "presale-prompt",
            version="2.0.0",
        ),
        definition(
            "ContextPolicy",
            "cpo_01111111-1111-7111-8111-111111111111",
            "presale-context",
            version="3.0.0",
        ),
    ]
    source = B1DefinitionSource(
        LeakySelectorRepo(objects),
        selectors={
            "agent_spec": {"kind": "AgentSpec", "namespace": "presale", "key": "presale-agent"},
            "prompt_package": {
                "kind": "PromptPackage",
                "namespace": "presale",
                "key": "presale-prompt",
            },
            "context_policy": {
                "kind": "ContextPolicy",
                "namespace": "presale",
                "key": "presale-context",
            },
        },
    )

    with pytest.raises(DefinitionResolutionError, match="DEFINITION_OUT_OF_SCOPE"):
        await source.resolve(tenant_id="tenant-demo")


@pytest.mark.asyncio
async def test_no_selector_and_no_id_raises_selector_missing():
    source = B1DefinitionSource(SelectorRepo([]))

    with pytest.raises(DefinitionResolutionError, match="DEFINITION_SELECTOR_MISSING"):
        await source.resolve(tenant_id="tenant-demo")


@pytest.mark.asyncio
async def test_selector_with_no_matching_active_definition_raises_not_found():
    source = B1DefinitionSource(
        SelectorRepo([]),
        selectors={
            "agent_spec": {"kind": "AgentSpec", "namespace": "presale", "key": "presale-agent"}
        },
    )

    with pytest.raises(DefinitionResolutionError, match="DEFINITION_NOT_FOUND"):
        await source.resolve(tenant_id="tenant-demo")
