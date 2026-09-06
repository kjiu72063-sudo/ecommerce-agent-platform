"""验证 tool-manifest 和 prompt-package Schema"""
import json
from pathlib import Path
from jsonschema import Draft202012Validator

schemas = [
    'schemas/definitions/tool-manifest.schema.json',
    'schemas/definitions/prompt-package.schema.json'
]

for schema_path in schemas:
    path = Path(schema_path)
    schema = json.loads(path.read_text(encoding='utf-8'))
    
    print(f'=== {path.name} ===')
    print(f'  标题: {schema.get("title", "N/A")}')
    print(f'  版本: {schema.get("x-contract-version", "N/A")}')
    print(f'  定义类型数: {len(schema.get("$defs", {}))}')
    
    try:
        Draft202012Validator.check_schema(schema)
        print(f'  Schema 验证: ✓ 有效')
    except Exception as e:
        print(f'  Schema 验证: ✗ 无效 - {e}')
    print()

print('所有 Schema 创建成功！')
