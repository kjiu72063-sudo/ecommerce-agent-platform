import pytest

from presale.definitions import B1DefinitionSource
from presale.knowledge import KnowledgeSource
from presale.runtime import PresaleRuntimeFactory


class Registry:
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
            and obj["metadata"]["scope"]["tenant_id"] == filter.tenant_id
        ]


def definition(kind, object_id, key, version="1.0.0"):
    return {
        "kind": kind,
        "metadata": {
            "id": object_id,
            "key": key,
            "namespace": "presale",
            "version": version,
            "content_digest": "sha256:" + "a" * 64,
            "scope": {"type": "tenant", "tenant_id": "tenant-demo"},
        },
        "status": {"phase": "active"},
    }


@pytest.mark.asyncio
async def test_factory_uses_b1_definition_source_for_runner():
    registry = Registry(
        [
            definition("AgentSpec", "agt_01111111-1111-7111-8111-111111111111", "presale-agent"),
            definition(
                "PromptPackage",
                "prm_01111111-1111-7111-8111-111111111111",
                "presale-prompt",
                "2.0.0",
            ),
            definition(
                "ContextPolicy",
                "cpo_01111111-1111-7111-8111-111111111111",
                "presale-context",
                "3.0.0",
            ),
        ]
    )
    factory = PresaleRuntimeFactory(
        definition_repository=registry,
        definition_selectors={
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
        sources=[
            KnowledgeSource(
                source_id="catalog-001",
                version="2026.09.01",
                tenant_id="tenant-demo",
                product_id="product-001",
                status="published",
                fields={"spec": {"season": "适合夏季使用"}},
            )
        ],
    )

    runner = factory.create_runner()
    config = await runner._definition_source.resolve(tenant_id="tenant-demo")

    assert config.configuration_refs["context_policy"] == "3.0.0"
    assert isinstance(runner._definition_source, B1DefinitionSource)
