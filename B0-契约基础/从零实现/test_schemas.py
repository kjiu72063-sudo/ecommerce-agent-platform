"""验证 JSON Schema 文件"""
import json
from pathlib import Path

schemas_dir = Path('schemas')

# 读取 Schema 文件
common_schema = json.loads((schemas_dir / 'common' / 'common-types.schema.json').read_text(encoding='utf-8'))
agent_spec_schema = json.loads((schemas_dir / 'definitions' / 'agent-spec.schema.json').read_text(encoding='utf-8'))

print('=== Schema 验证 ===')
print('common-types.schema.json:')
print(f'  标题: {common_schema.get("title", "N/A")}')
print(f'  版本: {common_schema.get("x-contract-version", "N/A")}')
print(f'  定义类型数: {len(common_schema.get("$defs", {}))}')

print('\nagent-spec.schema.json:')
print(f'  标题: {agent_spec_schema.get("title", "N/A")}')
print(f'  版本: {agent_spec_schema.get("x-contract-version", "N/A")}')
print(f'  定义类型数: {len(agent_spec_schema.get("$defs", {}))}')

# 使用 jsonschema 验证 Schema 本身
from jsonschema import Draft202012Validator

try:
    Draft202012Validator.check_schema(common_schema)
    print('\ncommon-types.schema.json: Schema 结构有效 ✓')
except Exception as e:
    print(f'\ncommon-types.schema.json: Schema 结构无效 ✗ - {e}')

try:
    Draft202012Validator.check_schema(agent_spec_schema)
    print('agent-spec.schema.json: Schema 结构有效 ✓')
except Exception as e:
    print(f'agent-spec.schema.json: Schema 结构无效 ✗ - {e}')

print('\nJSON Schema 创建成功！')
