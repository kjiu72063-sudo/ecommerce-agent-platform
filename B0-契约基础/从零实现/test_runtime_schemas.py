"""验证 task 和 agent-run Schema"""
import json
from pathlib import Path
from jsonschema import Draft202012Validator

schemas = [
    'schemas/runtime/task.schema.json',
    'schemas/runtime/agent-run.schema.json'
]

print('=== 运行对象 Schema 验证 ===')
print()

all_valid = True
for schema_path in schemas:
    path = Path(schema_path)
    schema = json.loads(path.read_text(encoding='utf-8'))
    
    title = schema.get('title', 'N/A')
    version = schema.get('x-contract-version', 'N/A')
    defs_count = len(schema.get('$defs', {}))
    
    try:
        Draft202012Validator.check_schema(schema)
        status = '✓ 有效'
    except Exception as e:
        status = f'✗ 无效 - {e}'
        all_valid = False
    
    print(f'{path.name}:')
    print(f'  标题: {title}')
    print(f'  版本: {version}')
    print(f'  定义类型数: {defs_count}')
    print(f'  验证: {status}')
    print()

if all_valid:
    print('所有运行对象 Schema 验证通过！')
else:
    print('部分 Schema 验证失败！')
