# B3 Context 引擎开发指南

> 文档版本：1.0.0
> 创建日期：2026-09-01
> 前置依赖：B2 状态与持久化
> 预计工期：3-4 周

---

## 一、B3 目标

实现 Context Engine，负责为模型调用组装最小、最相关的上下文快照。

### 1.1 核心职责

- 多来源 Context 采集（Task、Agent、Prompt、Memory、RAG、Tool 等）
- Token 预算管理
- 优先级排序与裁剪
- 数据脱敏
- Context 快照生成与持久化

### 1.2 不包含

- Agent 执行逻辑（B4）
- 实际的 RAG 检索实现（B6 业务 Agent）

## 二、Context 来源架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Context Engine                                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  Source Adapters                         │    │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐      │    │
│  │  │Task │ │Agent│ │RAG │ │Memory│ │Tool │ │Skill│      │    │
│  │  └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘      │    │
│  └─────┼───────┼───────┼───────┼───────┼───────┼──────────┘    │
│        │       │       │       │       │       │               │
│        ▼       ▼       ▼       ▼       ▼       ▼               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Token Budget Manager                        │    │
│  │  ┌──────────────────────────────────────────────┐       │    │
│  │  │ Priority Sorter → Budget Allocator → Trimmer │       │    │
│  │  └──────────────────────────────────────────────┘       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                     │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Context Package                             │    │
│  │  - sections: List[ContextSection]                       │    │
│  │  - total_tokens: int                                    │    │
│  │  - content_digest: str                                  │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## 三、开发任务分解

### 任务 1：Source Adapter 接口（第 1-2 天）

#### 3.1.1 适配器接口定义

```python
# B3-Context引擎/src/context/sources/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class ContextSection:
    """Context 片段"""
    type: str                    # 来源类型
    priority: int                # 优先级 0-100
    token_count: int             # Token 数量
    provenance_refs: list        # 来源引用
    content: str                 # 实际内容
    content_digest: str          # 内容摘要

class ContextSourceAdapter(ABC):
    """Context 来源适配器接口"""
    
    @abstractmethod
    async def fetch(
        self, 
        run_context: dict,
        token_budget: int
    ) -> Optional[ContextSection]:
        """
        获取 Context 片段
        
        Args:
            run_context: 运行上下文（包含 task_ref, agent_ref 等）
            token_budget: 分配给该来源的 token 预算
            
        Returns:
            ContextSection 或 None
        """
        pass
    
    @abstractmethod
    def get_source_type(self) -> str:
        """返回来源类型标识"""
        pass
    
    @abstractmethod
    def get_priority(self) -> int:
        """返回默认优先级"""
        pass
```

---

### 任务 2：实现各来源适配器（第 3-7 天）

#### 3.2.1 Task 来源适配器

```python
# B3-Context引擎/src/context/sources/task_source.py

class TaskSourceAdapter(ContextSourceAdapter):
    """Task 来源适配器"""
    
    def __init__(self, task_service):
        self.task_service = task_service
    
    async def fetch(self, run_context: dict, token_budget: int) -> Optional[ContextSection]:
        """获取 Task 信息"""
        task_id = run_context.get('task_id')
        if not task_id:
            return None
        
        task = await self.task_service.get_task(task_id)
        
        # 构建 Task 描述
        content = f"""
## 当前任务
- 标题：{task['spec']['title']}
- 意图：{task['spec']['intent']}
- 领域：{task['spec']['domain']}
- 优先级：{task['spec']['priority']}

## 任务输入
{self._format_payload(task['spec']['payload'])}

## 约束条件
{self._format_constraints(task['spec'])}
"""
        
        # 截断到预算
        content = self._truncate_to_budget(content, token_budget)
        
        return ContextSection(
            type="task",
            priority=100,  # 最高优先级
            token_count=self._count_tokens(content),
            provenance_refs=[task_id],
            content=content,
            content_digest=canonical_sha256(content)
        )
    
    def get_source_type(self) -> str:
        return "task"
    
    def get_priority(self) -> int:
        return 100
```

#### 3.2.2 AgentSpec 来源适配器

```python
# B3-Context引擎/src/context/sources/agent_source.py

class AgentSourceAdapter(ContextSourceAdapter):
    """AgentSpec 来源适配器"""
    
    def __init__(self, registry_service):
        self.registry = registry_service
    
    async def fetch(self, run_context: dict, token_budget: int) -> Optional[ContextSection]:
        """获取 Agent 定义"""
        agent_ref = run_context.get('agent_snapshot')
        if not agent_ref:
            return None
        
        agent = await self.registry.get_definition(agent_ref['id'])
        spec = agent['spec']
        
        content = f"""
## Agent 身份
- 目的：{spec['purpose']}
- 领域：{spec['domain']}

## 目标
{self._format_list(spec['goals'])}

## 非目标
{self._format_list(spec['non_goals'])}

## 可用技能
{self._format_bindings(spec.get('skill_bindings', []))}
"""
        
        content = self._truncate_to_budget(content, token_budget)
        
        return ContextSection(
            type="agent_spec",
            priority=95,
            token_count=self._count_tokens(content),
            provenance_refs=[agent_ref['id']],
            content=content,
            content_digest=canonical_sha256(content)
        )
    
    def get_source_type(self) -> str:
        return "agent_spec"
    
    def get_priority(self) -> int:
        return 95
```

#### 3.2.3 RAG 来源适配器

```python
# B3-Context引擎/src/context/sources/rag_source.py

class RAGSourceAdapter(ContextSourceAdapter):
    """RAG 知识库来源适配器"""
    
    def __init__(self, rag_tool, context_policy):
        self.rag_tool = rag_tool
        self.policy = context_policy
    
    async def fetch(self, run_context: dict, token_budget: int) -> Optional[ContextSection]:
        """从 RAG 检索相关内容"""
        query = self._build_query(run_context)
        
        if not query:
            return None
        
        # 调用 RAG Tool 检索
        results = await self.rag_tool.search(
            query=query,
            top_k=self.policy['skill_selection']['top_k'],
            token_limit=token_budget
        )
        
        if not results:
            return None
        
        # 格式化检索结果
        content = "## 相关知识\n\n"
        for i, result in enumerate(results, 1):
            content += f"### 来源 {i}: {result['title']}\n"
            content += f"{result['content']}\n\n"
            content += f"相关度: {result['score']:.2f}\n\n---\n\n"
        
        content = self._truncate_to_budget(content, token_budget)
        
        return ContextSection(
            type="rag_knowledge",
            priority=80,
            token_count=self._count_tokens(content),
            provenance_refs=[r['id'] for r in results],
            content=content,
            content_digest=canonical_sha256(content)
        )
    
    def _build_query(self, run_context: dict) -> Optional[str]:
        """构建 RAG 查询"""
        # 从 Task payload 提取查询关键词
        task_payload = run_context.get('task_payload', {})
        return task_payload.get('query') or task_payload.get('question')
    
    def get_source_type(self) -> str:
        return "rag_knowledge"
    
    def get_priority(self) -> int:
        return 80
```

#### 3.2.4 Memory 来源适配器

```python
# B3-Context引擎/src/context/sources/memory_source.py

class MemorySourceAdapter(ContextSourceAdapter):
    """Memory 来源适配器"""
    
    def __init__(self, memory_service, context_policy):
        self.memory = memory_service
        self.policy = context_policy
    
    async def fetch(self, run_context: dict, token_budget: int) -> Optional[ContextSection]:
        """获取相关记忆"""
        # 确定记忆作用域
        allowed_scopes = self.policy['memory_scope']['allowed_scopes']
        
        # 搜索相关记忆
        memories = await self.memory.search(
            query=self._build_memory_query(run_context),
            scopes=allowed_scopes,
            limit=10
        )
        
        if not memories:
            return None
        
        content = "## 历史记忆\n\n"
        for memory in memories:
            content += f"- {memory['content']}\n"
            content += f"  来源: {memory['source']} | 时间: {memory['created_at']}\n\n"
        
        content = self._truncate_to_budget(content, token_budget)
        
        return ContextSection(
            type="memory",
            priority=60,
            token_count=self._count_tokens(content),
            provenance_refs=[m['id'] for m in memories],
            content=content,
            content_digest=canonical_sha256(content)
        )
    
    def get_source_type(self) -> str:
        return "memory"
    
    def get_priority(self) -> int:
        return 60
```

#### 3.2.5 Tool Schema 来源适配器

```python
# B3-Context引擎/src/context/sources/tool_schema_source.py

class ToolSchemaSourceAdapter(ContextSourceAdapter):
    """Tool Schema 来源适配器"""
    
    def __init__(self, registry_service, context_policy):
        self.registry = registry_service
        self.policy = context_policy
    
    async def fetch(self, run_context: dict, token_budget: int) -> Optional[ContextSection]:
        """获取可用 Tool 的 Schema"""
        tool_refs = run_context.get('resolved_dependencies', {}).get('startup_tool_refs', [])
        
        if not tool_refs:
            return None
        
        content = "## 可用工具\n\n"
        tool_ids = []
        
        for ref in tool_refs[:self.policy['tool_selection']['max_visible_tools']]:
            tool = await self.registry.get_definition(ref['id'])
            tool_ids.append(ref['id'])
            
            content += f"### {tool['spec']['capability']}\n"
            content += f"- 提供者: {tool['spec']['provider']}\n"
            content += f"- 副作用: {tool['spec']['side_effect']}\n"
            content += f"- 输入 Schema: {self._summarize_schema(tool['spec']['input_schema_ref'])}\n\n"
        
        content = self._truncate_to_budget(content, token_budget)
        
        return ContextSection(
            type="tool_schema",
            priority=70,
            token_count=self._count_tokens(content),
            provenance_refs=tool_ids,
            content=content,
            content_digest=canonical_sha256(content)
        )
    
    def get_source_type(self) -> str:
        return "tool_schema"
    
    def get_priority(self) -> int:
        return 70
```

---

### 任务 3：Token Budget Manager（第 8-10 天）

#### 3.3.1 预算管理器

```python
# B3-Context引擎/src/context/budget_manager.py

from typing import List
from agent_platform_contracts.models import ContextSection

class TokenBudgetManager:
    """Token 预算管理器"""
    
    def __init__(self, policy: dict):
        self.policy = policy
        self.total_budget = policy['token_budget']['total_tokens']
        self.reserved_output = policy['token_budget']['reserved_output_tokens']
        self.available_input = self.total_budget - self.reserved_output
        self.per_source_budgets = policy['token_budget']['per_source']
    
    def allocate_budgets(self, sources: List[str]) -> dict:
        """为各来源分配 token 预算"""
        allocations = {}
        
        # 1. 按策略分配固定预算
        for source in sources:
            if source in self.per_source_budgets:
                allocations[source] = self.per_source_budgets[source]
            else:
                allocations[source] = 0
        
        # 2. 计算剩余预算
        allocated = sum(allocations.values())
        remaining = self.available_input - allocated
        
        # 3. 按优先级分配剩余预算
        if remaining > 0:
            high_priority_sources = [s for s in sources if allocations[s] == 0]
            per_source = remaining // len(high_priority_sources) if high_priority_sources else 0
            for source in high_priority_sources:
                allocations[source] = per_source
        
        return allocations
    
    def enforce_budget(self, sections: List[ContextSection]) -> List[ContextSection]:
        """强制执行预算限制"""
        # 按优先级排序
        sorted_sections = sorted(sections, key=lambda s: s.priority, reverse=True)
        
        result = []
        used_tokens = 0
        
        for section in sorted_sections:
            if used_tokens + section.token_count <= self.available_input:
                result.append(section)
                used_tokens += section.token_count
            else:
                # 截断到剩余预算
                remaining = self.available_input - used_tokens
                if remaining > 0:
                    truncated = self._truncate_section(section, remaining)
                    result.append(truncated)
                break
        
        return result
    
    def _truncate_section(self, section: ContextSection, max_tokens: int) -> ContextSection:
        """截断 Context 片段"""
        # 简单截断策略：保留开头
        truncated_content = self._truncate_text(section.content, max_tokens)
        
        return ContextSection(
            type=section.type,
            priority=section.priority,
            token_count=self._count_tokens(truncated_content),
            provenance_refs=section.provenance_refs,
            content=truncated_content,
            content_digest=canonical_sha256(truncated_content)
        )
```

---

### 任务 4：Context Engine 核心（第 11-14 天）

#### 3.4.1 Context Engine 实现

```python
# B3-Context引擎/src/context/engine.py

from typing import List, Dict
from .budget_manager import TokenBudgetManager
from .redactor import ContextRedactor

class ContextEngine:
    """Context 引擎核心"""
    
    def __init__(self, sources: Dict[str, ContextSourceAdapter], policy: dict):
        self.sources = sources
        self.policy = policy
        self.budget_manager = TokenBudgetManager(policy)
        self.redactor = ContextRedactor(policy.get('redaction', {}))
    
    async def build_context(self, run_context: dict) -> dict:
        """构建 Context Package"""
        # 1. 确定启用的来源
        enabled_sources = self._get_enabled_sources()
        
        # 2. 分配预算
        budget_allocations = self.budget_manager.allocate_budgets(enabled_sources)
        
        # 3. 并行获取各来源
        sections = await self._fetch_all_sources(run_context, budget_allocations)
        
        # 4. 过滤空结果
        sections = [s for s in sections if s is not None]
        
        # 5. 数据脱敏
        sections = [self.redactor.redact(s) for s in sections]
        
        # 6. 强制执行总预算
        sections = self.budget_manager.enforce_budget(sections)
        
        # 7. 计算总 token
        total_tokens = sum(s.token_count for s in sections)
        
        # 8. 生成摘要
        content_digest = canonical_sha256(
            [s.content for s in sections]
        )
        
        # 9. 构建 Context Package
        context_package = {
            "run_ref": {"kind": "AgentRun", "id": run_context['run_id']},
            "model_call_sequence": run_context.get('model_call_sequence', 1),
            "policy_ref": run_context.get('context_policy_ref'),
            "sections": [self._section_to_dict(s) for s in sections],
            "total_tokens": total_tokens,
            "redaction_summary": self.redactor.get_summary(),
            "content_digest": content_digest
        }
        
        return context_package
    
    async def _fetch_all_sources(
        self, 
        run_context: dict, 
        budgets: dict
    ) -> List[ContextSection]:
        """并行获取所有来源"""
        import asyncio
        
        tasks = []
        for source_type, adapter in self.sources.items():
            budget = budgets.get(source_type, 0)
            if budget > 0:
                tasks.append(adapter.fetch(run_context, budget))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 过滤异常
        valid_results = []
        for result in results:
            if isinstance(result, ContextSection):
                valid_results.append(result)
            elif isinstance(result, Exception):
                # 记录错误但不中断
                print(f"Source fetch error: {result}")
        
        return valid_results
    
    def _get_enabled_sources(self) -> List[str]:
        """获取启用的来源"""
        enabled = []
        for rule in self.policy.get('source_rules', []):
            if rule['effect'] == 'allow':
                enabled.append(rule['source'])
        return enabled
```

---

### 任务 5：数据脱敏（第 15-16 天）

#### 3.5.1 脱敏器实现

```python
# B3-Context引擎/src/context/redactor.py

import re

class ContextRedactor:
    """Context 数据脱敏器"""
    
    # Secret 模式
    SECRET_PATTERNS = [
        (r'\bsk-[A-Za-z0-9_-]{20,}\b', '[API_KEY_REDACTED]'),
        (r'\b(?:password|passwd|pwd)\s*[=:]\s*\S+', '[PASSWORD_REDACTED]'),
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL_REDACTED]'),
        (r'\b\d{16,19}\b', '[CARD_NUMBER_REDACTED]'),
    ]
    
    def __init__(self, policy: dict):
        self.policy = policy
        self.secret_count = 0
        self.pii_count = 0
    
    def redact(self, section: ContextSection) -> ContextSection:
        """对 Context 片段进行脱敏"""
        content = section.content
        
        # 1. 脱敏 Secret
        if self.policy.get('redact_secrets', True):
            content, count = self._redact_secrets(content)
            self.secret_count += count
        
        # 2. 脱敏 PII
        pii_mode = self.policy.get('pii_mode', 'mask')
        if pii_mode != 'none':
            content, count = self._redact_pii(content, pii_mode)
            self.pii_count += count
        
        # 返回脱敏后的片段
        return ContextSection(
            type=section.type,
            priority=section.priority,
            token_count=self._count_tokens(content),
            provenance_refs=section.provenance_refs,
            content=content,
            content_digest=canonical_sha256(content)
        )
    
    def _redact_secrets(self, content: str) -> tuple:
        """脱敏 Secret"""
        count = 0
        for pattern, replacement in self.SECRET_PATTERNS:
            matches = re.findall(pattern, content)
            count += len(matches)
            content = re.sub(pattern, replacement, content)
        return content, count
    
    def _redact_pii(self, content: str, mode: str) -> tuple:
        """脱敏 PII"""
        count = 0
        
        if mode == 'mask':
            # 手机号
            phone_pattern = r'\b1[3-9]\d{9}\b'
            matches = re.findall(phone_pattern, content)
            count += len(matches)
            content = re.sub(phone_pattern, '[PHONE_REDACTED]', content)
        
        elif mode == 'remove':
            # 完全移除
            pass
        
        return content, count
    
    def get_summary(self) -> dict:
        """获取脱敏摘要"""
        return {
            "secret_count": self.secret_count,
            "pii_count": self.pii_count
        }
```

---

## 四、关键知识点

### 4.1 优先级排序

```python
# 来源优先级定义
PRIORITIES = {
    "task": 100,           # 最高：当前任务
    "agent_spec": 95,      # Agent 定义
    "prompt": 90,          # 固定指令
    "rag_knowledge": 80,   # RAG 检索结果
    "tool_schema": 70,     # 可用工具
    "memory": 60,          # 历史记忆
    "thread": 50,          # 对话历史
}
```

### 4.2 Token 计算

```python
# 简单的 token 估算（实际应使用 tiktoken）
def count_tokens(text: str) -> int:
    """估算 token 数量"""
    # 粗略估算：1 个中文字符 ≈ 2 token
    # 1 个英文单词 ≈ 1.3 token
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    return chinese_chars * 2 + int(english_words * 1.3)
```

### 4.3 Context 快照持久化

```python
# 保存 Context 快照用于审计和恢复
async def persist_context_snapshot(context_package: dict) -> str:
    """持久化 Context 快照"""
    artifact = {
        "artifact_type": "context_snapshot",
        "media_type": "application/json",
        "content": context_package,
        "content_digest": context_package['content_digest']
    }
    artifact_id = await artifact_service.create(artifact)
    return artifact_id
```

---

## 五、验收标准

- [ ] 支持所有 Context 来源类型
- [ ] Token 预算正确分配和执行
- [ ] 优先级排序正确
- [ ] 数据脱敏有效
- [ ] Context Package 结构符合 B0 契约
- [ ] 内容摘要计算稳定
- [ ] 单元测试覆盖率 > 80%

---

## 六、下一步

完成 B3 后，进入 B4 Agent 执行器开发。
