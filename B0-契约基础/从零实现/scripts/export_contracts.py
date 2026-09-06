"""B0 契约包导出脚本

从 Pydantic 模型导出 JSON Schema 和示例文件。
确保重复生成得到稳定内容和摘要。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

# 添加 src 到路径
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def canonical_json(value: Any) -> bytes:
    """返回稳定的 UTF-8 JSON 字节序列"""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    """计算 SHA-256 摘要"""
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def export_json_schema(output_dir: Path) -> list[dict]:
    """导出 JSON Schema 文件"""
    schemas = []

    # 遍历所有 Schema 文件
    for schema_dir in [ROOT / "schemas" / "common", ROOT / "schemas" / "definitions", ROOT / "schemas" / "runtime"]:
        for path in sorted(schema_dir.glob("*.schema.json")):
            relative_path = path.relative_to(ROOT)
            content = path.read_bytes()
            digest = "sha256:" + hashlib.sha256(content).hexdigest()

            schemas.append({
                "path": str(relative_path).replace("\\", "/"),
                "digest": digest,
                "size_bytes": len(content)
            })

    return schemas


def export_examples(output_dir: Path) -> list[dict]:
    """导出示例文件"""
    examples = []

    # 有效示例
    for path in sorted((ROOT / "examples" / "valid").glob("*.json")):
        relative_path = path.relative_to(ROOT)
        content = path.read_bytes()
        digest = "sha256:" + hashlib.sha256(content).hexdigest()

        examples.append({
            "path": str(relative_path).replace("\\", "/"),
            "type": "valid",
            "digest": digest,
            "size_bytes": len(content)
        })

    # 无效示例
    for path in sorted((ROOT / "examples" / "invalid").glob("*.json")):
        relative_path = path.relative_to(ROOT)
        content = path.read_bytes()
        digest = "sha256:" + hashlib.sha256(content).hexdigest()

        examples.append({
            "path": str(relative_path).replace("\\", "/"),
            "type": "invalid",
            "digest": digest,
            "size_bytes": len(content)
        })

    return examples


def export_state_machines(output_dir: Path) -> list[dict]:
    """导出状态机文件"""
    state_machines = []

    for path in sorted((ROOT / "state-machines").glob("*.json")):
        relative_path = path.relative_to(ROOT)
        content = path.read_bytes()
        digest = "sha256:" + hashlib.sha256(content).hexdigest()

        state_machines.append({
            "path": str(relative_path).replace("\\", "/"),
            "digest": digest,
            "size_bytes": len(content)
        })

    return state_machines


def generate_manifest() -> dict:
    """生成合同清单"""
    manifest = {
        "contract_version": "0.2.0",
        "api_version": "agent-platform/v1alpha1",
        "generated_at": "2026-09-01T00:00:00Z",
        "summary": {
            "total_schemas": 0,
            "total_examples": 0,
            "total_state_machines": 0
        },
        "generated_files": []
    }

    # 导出 Schema
    schemas = export_json_schema(ROOT)
    manifest["summary"]["total_schemas"] = len(schemas)
    manifest["generated_files"].extend(schemas)

    # 导出示例
    examples = export_examples(ROOT)
    manifest["summary"]["total_examples"] = len(examples)
    manifest["generated_files"].extend(examples)

    # 导出状态机
    state_machines = export_state_machines(ROOT)
    manifest["summary"]["total_state_machines"] = len(state_machines)
    manifest["generated_files"].extend(state_machines)

    # 计算清单本身的摘要
    manifest_content = canonical_json(manifest)
    manifest["self_digest"] = "sha256:" + hashlib.sha256(manifest_content).hexdigest()

    return manifest


def main():
    """主函数"""
    print("=== B0 契约包导出 ===\n")

    # 生成清单
    manifest = generate_manifest()

    # 输出清单
    output_path = ROOT / "contract-manifest.json"
    output_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    # 打印摘要
    print(f"清单已生成: {output_path}")
    print(f"\n摘要:")
    print(f"  Schema 文件: {manifest['summary']['total_schemas']}")
    print(f"  示例文件: {manifest['summary']['total_examples']}")
    print(f"  状态机文件: {manifest['summary']['total_state_machines']}")
    print(f"  总文件数: {len(manifest['generated_files'])}")
    print(f"\n清单摘要: {manifest['self_digest'][:30]}...")

    # 验证稳定性
    print("\n验证生成稳定性...")
    manifest2 = generate_manifest()
    if manifest["self_digest"] == manifest2["self_digest"]:
        print("✓ 重复生成得到相同摘要")
    else:
        print("✗ 重复生成摘要不同!")
        return 1

    print("\n导出完成！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
