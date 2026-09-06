"""验证 skill-manifest.schema.json"""
import json
from pathlib import Path
from jsonschema import Draft202012Validator

schema_path = Path('schemas/definitions/skill-manifest.schema.json')
schema = json.loads(schema_path.read_text(encoding='utf-8'))

print('=== skill-manifest.schema.json 验证 ===')
print(f'标题: {schema.get("title", "N/A")}')
print(f'版本: {schema.get("x-contract-version", "N/A")}')
print(f'定义类型数: {len(schema.get("$defs", {}))}')

try:
    Draft202012Validator.check_schema(schema)
    print('Schema 结构验证: 有效 ✓')
except Exception as e:
    print(f'Schema 结构验证: 无效 ✗ - {e}')

print('创建成功！')
