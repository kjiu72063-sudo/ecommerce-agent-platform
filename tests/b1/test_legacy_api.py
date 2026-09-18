"""B1 能力注册中心 API 测试脚本"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path("src")))

from path_config import B0_EXAMPLES
from registry import DefinitionFilter, InMemoryDefinitionRepository, RegistryService


async def test_api():
    # 创建服务
    repo = InMemoryDefinitionRepository()
    service = RegistryService(repo)

    # 加载示例
    b0_root = B0_EXAMPLES / "valid"

    print("=== B1 能力注册中心 API 测试 ===")
    print()

    # 1. 注册 AgentSpec（修改初始状态为 draft 以便测试迁移）
    print("1. 注册 AgentSpec...")
    agent_spec = json.loads((b0_root / "agent-spec.json").read_text(encoding="utf-8"))
    agent_spec["status"]["phase"] = "draft"  # 修改为 draft 状态
    result = await service.register_definition(
        kind="agent-spec", payload=agent_spec, actor={"actor_type": "user", "actor_id": "usr_test"}
    )
    agent_id = result["id"]
    digest = result["content_digest"]
    print(f"   ID: {agent_id}")
    print(f"   Digest: {digest[:30]}...")
    print()

    # 2. 注册 SkillManifest
    print("2. 注册 SkillManifest...")
    skill = json.loads((b0_root / "skill-manifest.json").read_text(encoding="utf-8"))
    result = await service.register_definition(
        kind="skill-manifest", payload=skill, actor={"actor_type": "user", "actor_id": "usr_test"}
    )
    skill_id = result["id"]
    print(f"   ID: {skill_id}")
    print()

    # 3. 注册 ToolManifest
    print("3. 注册 ToolManifest...")
    tool = json.loads((b0_root / "tool-manifest.json").read_text(encoding="utf-8"))
    result = await service.register_definition(
        kind="tool-manifest", payload=tool, actor={"actor_type": "user", "actor_id": "usr_test"}
    )
    tool_id = result["id"]
    print(f"   ID: {tool_id}")
    print()

    # 4. 查询列表
    print("4. 查询所有 AgentSpec...")
    results = await service.list_definitions(DefinitionFilter(kind="AgentSpec"))
    print(f"   找到 {len(results)} 个")
    print()

    # 5. 获取详情
    print("5. 获取 AgentSpec 详情...")
    obj = await service.get_definition(agent_id)
    print(f"   Kind: {obj['kind']}")
    print(f"   Key: {obj['metadata']['key']}")
    print(f"   Version: {obj['metadata']['version']}")
    print(f"   Phase: {obj['status']['phase']}")
    print()

    # 6. 状态迁移：draft -> testing
    print("6. 状态迁移：draft -> testing...")
    result = await service.transition_state(agent_id, "testing", reason="开始测试")
    print(f"   结果: {result['phase']}")
    print()

    # 7. 状态迁移：testing -> awaiting_approval
    print("7. 状态迁移：testing -> awaiting_approval...")
    result = await service.transition_state(
        agent_id, "awaiting_approval", reason="测试通过，等待审批"
    )
    print(f"   结果: {result['phase']}")
    print()

    # 8. 状态迁移：awaiting_approval -> approved
    print("8. 状态迁移：awaiting_approval -> approved...")
    result = await service.transition_state(agent_id, "approved", reason="审批通过")
    print(f"   结果: {result['phase']}")
    print()

    # 9. 状态迁移：approved -> active
    print("9. 状态迁移：approved -> active...")
    result = await service.transition_state(agent_id, "active", reason="激活")
    print(f"   结果: {result['phase']}")
    print()

    # 10. 检查版本历史
    print("10. 检查版本历史...")
    versions = await service.repo.get_versions(agent_id)
    print(f"   版本数: {len(versions)}")
    print()

    # 11. 检查依赖关系
    print("11. 检查依赖关系...")
    deps = await service.repo.get_dependencies(agent_id, "1.0.0")
    print(f"   依赖数: {len(deps)}")
    for dep in deps:
        target_id = dep["target_id"][:20]
        print(f"   - {dep['dependency_type']}: {target_id}...")
    print()

    print("=== 所有测试通过！ ===")


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(test_api())
