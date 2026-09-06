# 第二步：models.py 基础部分 - 导入与常量

> 本节开始创建最核心的文件：models.py

---

## 文件位置
`src/agent_platform_contracts/models.py`

## 代码讲解

### 1. 文件头部与导入

```python
"""B0 contract reference models.

The models are the executable source for the JSON Schema 2020-12 artifacts.
They intentionally reject undeclared fields and encode cross-field invariants
that JSON Schema alone cannot express without implementation-specific code.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, ClassVar, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator
```

**逐行解释**：

| 代码 | 作用 |
|---|---|
| `from __future__ import annotations` | 支持 Python 3.9+ 的类型注解语法 |
| `datetime` | 日期时间类型 |
| `Decimal` | 精确小数（用于金额计算） |
| `StrEnum` | 字符串枚举基类 |
| `Annotated` | 带元数据的类型注解 |
| `Literal` | 字面量类型 |
| `BaseModel` | Pydantic 模型基类 |
| `Field` | 字段定义和约束 |
| `field_validator` | 字段级验证器 |
| `model_validator` | 模型级验证器 |

### 2. 常量定义

```python
API_VERSION = "agent-platform/v1alpha1"

# 语义版本正则
SEMVER_PATTERN = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"

# SHA-256 摘要正则
DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"

# UUIDv7 正则（版本号必须是 7）
UUID7_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"

# 资源 ID 正则（带类型前缀）
RESOURCE_ID_PATTERN = rf"^(?:ten|usr|prj|agt|skl|tol|prm|mpo|cpo|lop|pep|tsk|run|ckp|tcl|apr|art|evt)_{UUID7_PATTERN}$"
```

**关键知识点**：

1. **API_VERSION**：所有资源对象共享的 API 版本号
2. **语义版本（SemVer）**：`主版本.次版本.修订号`，如 `1.0.0`
3. **SHA-256 摘要**：用于验证内容完整性
4. **UUIDv7**：带时间戳的 UUID，版本号必须是 7
5. **资源 ID 前缀**：每种资源类型有唯一前缀

### 3. 资源 ID 前缀表

```python
# 资源类型 → ID 前缀映射
KIND_PREFIX: dict[str, str] = {
    "AgentSpec": "agt_",           # Agent 定义
    "SkillManifest": "skl_",       # 技能清单
    "ToolManifest": "tol_",        # 工具清单
    "PromptPackage": "prm_",       # Prompt 包
    "ModelPolicy": "mpo_",         # 模型策略
    "ContextPolicy": "cpo_",       # Context 策略
    "LoopProfile": "lop_",         # Loop 配置
    "PermissionProfile": "pep_",   # 权限配置
    "Task": "tsk_",                # 任务
    "AgentRun": "run_",            # Agent 运行
    "Checkpoint": "ckp_",          # 检查点
    "ToolCall": "tcl_",            # 工具调用
    "Approval": "apr_",            # 审批
    "Artifact": "art_",            # 产物
    "Event": "evt_",               # 事件
}
```

**为什么需要前缀？**
- 快速识别资源类型
- 防止 ID 冲突
- 便于日志和调试

---

## 下一步

接下来我们将创建 Pydantic 基础模型和类型别名。
