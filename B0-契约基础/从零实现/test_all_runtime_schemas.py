"""验证所有运行对象 Schema"""
import json
from pathlib import Path
from jsonschema import Draft202012Validator

schemas_dir = Path('schemas/runtime')
schemas = list(schemas_dir.glob('*.schema.json'))

print('=== 运行对象 Schema 验证 ===')
print(f'共 {len(schemas)} 个文件\n')

all_valid = True
for schema_path in sorted(schemas):
    schema = json.loads(schema_path.read_text(encoding='utf-8'))
    
    title = schema.get('title', 'N/A')
    version = schema.get('x-contract-version', 'N/A')
    defs_count = len(schema.get('$defs', {}))
    
    try:
        Draft202012Validator.check_schema(schema)
        status = '✓'
    except Exception as e:
        status = f'✗ {e}'
        all_valid = False
    
    print(f'{schema_path.name}:')
    print(f'  标题: {title}')
    print(f'  版本: {version}')
    print(f'  定义类型数: {defs_count}')
    print(f'  验证: {status}')
    print()

if all_valid:
    print('所有运行对象 Schema 验证通过！')
else:
    print('部分 Schema 验证失败！')
