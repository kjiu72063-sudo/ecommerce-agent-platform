# B5 Loop 引擎开发指南

> **⚠️ 已废弃**：本文件是 B5 的早期规划文档（2026-09-01），已被实际实现取代。
> 权威来源：
> - 设计：`docs/spec-b5-loop-engine.md`
> - 领域模型：`docs/domain-model-b4b6.md`
> - 领域决策：`docs/domain-decisions.md`（D-B9~D-B14）
> - ADR：`docs/adr/0001-agent-protocol-step-context.md`
> - 复盘：`docs/retro-b5b6-loop-engine.md`

> 文档版本：1.0.0（已废弃）
> 创建日期：2026-09-01
> 废弃日期：2026-09-21
> 前置依赖：B4 Agent 执行器
> 预计工期：3-4 周（实际 1 天完成）

---

## 一、B5 目标

实现 Loop Engine，负责 Agent 的有界迭代执行，包括观察、验证、修正和停止策略。

### 1.1 核心职责

- 迭代策略实现（single_pass/react/repair/ralph/review_refine）
- 评估器框架
- 进度追踪与恢复
- 预算控制与硬停止

### 1.2 Loop 策略类型

| 策略 | 描述 | 适用场景 |
|---|---|---|
| `single_pass` | 单次执行，无迭代 | 简单问答 |
| `react` | 观察-行动循环 | 工具调用 |
| `repair` | 失败后修复重试 | 代码生成 |
| `ralph` | 外部验证器驱动 | 需要外部评估的任务 |
| `review_refine` | 审查-改进循环 | 内容生成 |

## 二、Loop 执行流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    Loop Engine                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  Loop Controller                        │    │
│  │  ┌──────────────────────────────────────────────┐       │    │
│  │  │ while iteration < max_iterations:            │       │    │
│  │  │     1. Observe (收集信息)                    │       │    │
│  │  │     2. Think (推理决策)                      │       │    │
│  │  │     3. Act (执行动作)                        │       │    │
│  │  │     4. Evaluate (评估结果)                   │       │    │
│  │  │     5. Check Stop Conditions                 │       │    │
│  │  └──────────────────────────────────────────────┘       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                     │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  Evaluators                              │    │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                      │    │
│  │  │Model│ │Rule │ │Human│ │Tool │                      │    │
│  │  └─────┘ └─────┘ └─────┘ └─────┘                      │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                     │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  Stop Conditions                        │    │
│  │  - Success: 任务完成                                    │    │
│  │  - Failure: 不可恢复错误                                │    │
│  │  - Budget: 预算耗尽                                     │    │
│  │  - Human: 人工停止                                      │    │
│  │  - Validator: 验证器通过                                │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## 三、开发任务分解

### 任务 1：Loop Controller（第 1-4 天）

#### 3.1.1 核心控制器

```python
# B5-Loop引擎/src/loop/controller.py

from typing import Optional, Callable
from datetime import datetime, timezone

class LoopController:
    """Loop 控制器"""
    
    def __init__(
        self,
        strategy: str,
        profile: dict,
        harness,
        evaluators: list,
        event_store
    ):
        self.strategy = strategy
        self.profile = profile
        self.harness = harness
        self.evaluators = evaluators
        self.events = event_store
        
        # 预算追踪
        self.usage = {
            "iterations": 0,
            "wall_time_seconds": 0,
            "model_tokens": 0,
            "cost_usd": 0,
            "tool_calls": 0
        }
        self.start_time = None
    
    async def execute(
        self,
        run_context: dict,
        model_client,
        initial_state: dict = None
    ) -> dict:
        """执行 Loop"""
        self.start_time = datetime.now(timezone.utc)
        state = initial_state or {}
        
        max_iterations = self.profile['max_iterations']
        
        while self.usage['iterations'] < max_iterations:
            self.usage['iterations'] += 1
            
            # 发布迭代开始事件
            await self.events.publish(
                event_type="loop.iteration_started",
                subject_ref={"kind": "AgentRun", "id": run_context['run_id']},
                data={"iteration": self.usage['iterations']}
            )
            
            try:
                # 1. 观察
                observation = await self._observe(run_context, state)
                
                # 2. 推理
                thought = await self._think(run_context, state, observation, model_client)
                
                # 3. 执行
                action_result = await self._act(run_context, thought)
                
                # 4. 评估
                evaluation = await self._evaluate(run_context, state, action_result)
                
                # 5. 更新状态
                state = self._update_state(state, observation, thought, action_result, evaluation)
                
                # 6. 检查停止条件
                should_stop, reason = await self._check_stop_conditions(state, evaluation)
                
                if should_stop:
                    await self.events.publish(
                        event_type="loop.stopped",
                        subject_ref={"kind": "AgentRun", "id": run_context['run_id']},
                        data={"reason": reason, "iteration": self.usage['iterations']}
                    )
                    return {
                        "status": "completed",
                        "reason": reason,
                        "final_state": state,
                        "usage": self.usage
                    }
                
                # 7. 检查预算
                if self._check_budget_exceeded():
                    return {
                        "status": "budget_exceeded",
                        "final_state": state,
                        "usage": self.usage
                    }
                
            except Exception as e:
                # 错误处理
                error_result = await self._handle_error(e, run_context, state)
                
                if error_result['action'] == 'retry':
                    continue
                elif error_result['action'] == 'abort':
                    return {
                        "status": "error",
                        "error": str(e),
                        "final_state": state,
                        "usage": self.usage
                    }
        
        # 达到最大迭代次数
        return {
            "status": "max_iterations_reached",
            "final_state": state,
            "usage": self.usage
        }
    
    async def _observe(self, run_context: dict, state: dict) -> dict:
        """观察阶段：收集信息"""
        # 构建 Context
        context_package = await self.harness.context.build_context(run_context)
        
        return {
            "context": context_package,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def _think(
        self, 
        run_context: dict, 
        state: dict, 
        observation: dict,
        model_client
    ) -> dict:
        """推理阶段：模型决策"""
        # 准备 Prompt
        prompt = self._build_thinking_prompt(state, observation)
        
        # 调用模型
        response = await model_client.call(
            context=observation['context'],
            prompt=prompt
        )
        
        # 解析响应
        parsed = self._parse_model_response(response)
        
        # 追踪 token 使用
        self.usage['model_tokens'] += response.get('usage', {}).get('total_tokens', 0)
        
        return parsed
    
    async def _act(self, run_context: dict, thought: dict) -> dict:
        """执行阶段：执行动作"""
        action = thought.get('action')
        
        if action == 'tool_call':
            # 调用 Tool
            tool_ref = thought['tool_ref']
            input_data = thought['tool_input']
            
            result = await self.harness.tool_executor.execute_tool_call(
                run_id=run_context['run_id'],
                tool_ref=tool_ref,
                input_data=input_data,
                requested_by={"actor_type": "agent", "actor_id": run_context['run_id']}
            )
            
            self.usage['tool_calls'] += 1
            
            return {"type": "tool_call", "result": result}
        
        elif action == 'respond':
            # 直接响应
            return {"type": "respond", "content": thought['response']}
        
        else:
            return {"type": "no_action"}
    
    async def _evaluate(
        self, 
        run_context: dict, 
        state: dict, 
        action_result: dict
    ) -> dict:
        """评估阶段：评估结果"""
        evaluations = []
        
        for evaluator in self.evaluators:
            result = await evaluator.evaluate(
                run_context=run_context,
                state=state,
                action_result=action_result
            )
            evaluations.append(result)
        
        # 综合评估
        return {
            "scores": evaluations,
            "passed": all(e['passed'] for e in evaluations),
            "feedback": self._combine_feedback(evaluations)
        }
    
    async def _check_stop_conditions(
        self, 
        state: dict, 
        evaluation: dict
    ) -> tuple:
        """检查停止条件"""
        for condition in self.profile['stop_conditions']:
            condition_type = condition['condition_type']
            
            if condition_type == 'success':
                if self._check_success(state, evaluation):
                    return True, "success"
            
            elif condition_type == 'failure':
                if self._check_failure(state, evaluation):
                    return True, "failure"
            
            elif condition_type == 'budget':
                if self._check_budget_exceeded():
                    return True, "budget"
            
            elif condition_type == 'human_stop':
                if await self._check_human_stop():
                    return True, "human_stop"
            
            elif condition_type == 'validator':
                if await self._check_validator(state, evaluation):
                    return True, "validator"
        
        return False, None
    
    def _check_budget_exceeded(self) -> bool:
        """检查预算是否超限"""
        max_wall_time = self.profile['max_wall_time_seconds']
        max_tokens = self.profile['max_model_tokens']
        max_cost = self.profile['max_cost_usd']
        
        elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        
        return (
            elapsed > max_wall_time or
            self.usage['model_tokens'] > max_tokens or
            self.usage['cost_usd'] > max_cost
        )
```

---

### 任务 2：策略实现（第 5-8 天）

#### 3.2.1 React 策略

```python
# B5-Loop引擎/src/loop/strategies/react.py

class ReactStrategy:
    """React 策略：观察-行动循环"""
    
    def __init__(self, controller: LoopController):
        self.controller = controller
    
    def _build_thinking_prompt(self, state: dict, observation: dict) -> str:
        """构建 React 推理 Prompt"""
        return f"""
## 当前状态
{self._format_state(state)}

## 观察结果
{self._format_observation(observation)}

## 可用工具
{self._format_tools(observation.get('available_tools', []))}

## 指令
1. 分析当前情况
2. 决定下一步行动
3. 如果任务完成，返回 is_complete=true

请以 JSON 格式返回你的决策：
{{
    "thought": "你的推理过程",
    "action": "tool_call 或 respond",
    "tool_ref": "工具引用（如果调用工具）",
    "tool_input": "工具输入（如果调用工具）",
    "response": "最终响应（如果完成）",
    "is_complete": true/false
}}
"""
    
    def _parse_model_response(self, response: str) -> dict:
        """解析模型响应"""
        import json
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取 JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
            
            return {
                "thought": response,
                "action": "respond",
                "response": response,
                "is_complete": True
            }
```

#### 3.2.2 Repair 策略

```python
# B5-Loop引擎/src/loop/strategies/repair.py

class RepairStrategy:
    """Repair 策略：失败后修复重试"""
    
    def __init__(self, controller: LoopController):
        self.controller = controller
        self.max_retries = 3
        self.retry_count = 0
    
    def _build_thinking_prompt(self, state: dict, observation: dict) -> str:
        """构建 Repair 推理 Prompt"""
        error_info = state.get('last_error')
        
        if error_info and self.retry_count < self.max_retries:
            self.retry_count += 1
            return f"""
## 上次执行失败
- 错误：{error_info['message']}
- 原因：{error_info.get('cause', '未知')}

## 当前状态
{self._format_state(state)}

## 指令
分析错误原因，提出修复方案，并重新尝试。

请以 JSON 格式返回：
{{
    "thought": "错误分析和修复思路",
    "action": "tool_call",
    "tool_ref": "工具引用",
    "tool_input": "修复后的输入",
    "is_complete": false
}}
"""
        else:
            # 重试次数用尽，放弃
            return f"""
## 当前状态
{self._format_state(state)}

## 指令
已经重试 {self.max_retries} 次仍然失败。请总结问题并返回最终结果。

请以 JSON 格式返回：
{{
    "thought": "问题总结",
    "action": "respond",
    "response": "最终结果或错误说明",
    "is_complete": true
}}
"""
```

#### 3.2.3 Review-Refine 策略

```python
# B5-Loop引擎/src/loop/strategies/review_refine.py

class ReviewRefineStrategy:
    """Review-Refine 策略：审查-改进循环"""
    
    def __init__(self, controller: LoopController):
        self.controller = controller
        self.current_draft = None
    
    def _build_thinking_prompt(self, state: dict, observation: dict) -> str:
        """构建 Review-Refine 推理 Prompt"""
        if self.current_draft is None:
            # 第一轮：生成初稿
            return f"""
## 任务
{self._format_task(observation)}

## 指令
请生成初稿。

请以 JSON 格式返回：
{{
    "thought": "创作思路",
    "action": "generate",
    "draft": "初稿内容",
    "is_complete": false
}}
"""
        else:
            # 后续轮次：审查并改进
            feedback = state.get('review_feedback', '')
            return f"""
## 当前草稿
{self.current_draft}

## 审查反馈
{feedback}

## 指令
根据审查反馈改进草稿。

请以 JSON 格式返回：
{{
    "thought": "改进思路",
    "action": "refine",
    "draft": "改进后的草稿",
    "is_complete": false
}}
"""
    
    async def _evaluate(self, run_context: dict, state: dict, action_result: dict) -> dict:
        """评估草稿质量"""
        if action_result['type'] == 'generate':
            self.current_draft = action_result.get('draft')
        
        # 使用评估器评估
        evaluation = await super()._evaluate(run_context, state, action_result)
        
        # 如果通过评估，标记为完成
        if evaluation['passed']:
            return {
                **evaluation,
                "is_complete": True,
                "final_output": self.current_draft
            }
        
        return evaluation
```

---

### 任务 3：评估器框架（第 9-12 天）

#### 3.3.1 评估器接口

```python
# B5-Loop引擎/src/loop/evaluators/base.py

from abc import ABC, abstractmethod

class Evaluator(ABC):
    """评估器接口"""
    
    @abstractmethod
    async def evaluate(
        self,
        run_context: dict,
        state: dict,
        action_result: dict
    ) -> dict:
        """
        评估结果
        
        Returns:
            {
                "passed": bool,
                "score": float,
                "feedback": str,
                "details": dict
            }
        """
        pass

class ModelEvaluator(Evaluator):
    """模型评估器：使用 LLM 评估质量"""
    
    def __init__(self, model_client, criteria: list):
        self.model = model_client
        self.criteria = criteria
    
    async def evaluate(self, run_context: dict, state: dict, action_result: dict) -> dict:
        """使用模型评估"""
        prompt = f"""
## 评估标准
{self._format_criteria(self.criteria)}

## 待评估内容
{self._format_content(action_result)}

## 指令
请根据评估标准对待评估内容进行评分（0-100）并给出反馈。

请以 JSON 格式返回：
{{
    "score": 85,
    "passed": true,
    "feedback": "详细的评估反馈",
    "details": {{
        "criteria_scores": {{"标准1": 90, "标准2": 80}}
    }}
}}
"""
        
        response = await self.model.call(prompt=prompt)
        return self._parse_evaluation(response)

class RuleEvaluator(Evaluator):
    """规则评估器：基于规则评估"""
    
    def __init__(self, rules: list):
        self.rules = rules
    
    async def evaluate(self, run_context: dict, state: dict, action_result: dict) -> dict:
        """基于规则评估"""
        scores = []
        feedbacks = []
        
        for rule in self.rules:
            result = self._apply_rule(rule, action_result)
            scores.append(result['score'])
            feedbacks.append(result['feedback'])
        
        avg_score = sum(scores) / len(scores) if scores else 0
        
        return {
            "passed": avg_score >= 70,
            "score": avg_score,
            "feedback": "\n".join(feedbacks),
            "details": {"rule_scores": dict(zip([r['name'] for r in self.rules], scores))}
        }
    
    def _apply_rule(self, rule: dict, action_result: dict) -> dict:
        """应用单条规则"""
        rule_type = rule['type']
        
        if rule_type == 'length':
            content = action_result.get('content', '')
            min_len = rule.get('min_length', 0)
            max_len = rule.get('max_length', float('inf'))
            
            if min_len <= len(content) <= max_len:
                return {"score": 100, "feedback": f"长度符合要求"}
            else:
                return {"score": 0, "feedback": f"长度不符合要求（{min_len}-{max_len}）"}
        
        elif rule_type == 'format':
            # 格式检查
            pass
        
        return {"score": 50, "feedback": "未应用规则"}

class HumanEvaluator(Evaluator):
    """人工评估器：等待人工反馈"""
    
    def __init__(self, approval_service):
        self.approval_service = approval_service
    
    async def evaluate(self, run_context: dict, state: dict, action_result: dict) -> dict:
        """等待人工评估"""
        # 创建审批请求
        approval = await self.approval_service.request_approval(
            subject_ref={"kind": "AgentRun", "id": run_context['run_id']},
            requester={"actor_type": "system", "actor_id": "loop_engine"},
            approval_type="human_evaluation",
            risk_summary="需要人工评估输出质量",
            requested_actions=[{"action": "evaluate", "resource": "output"}],
            input_digest=canonical_sha256(action_result),
            policy_snapshot={},
            required_approvers=[{"role": "reviewer", "count": 1}],
            ttl_seconds=3600
        )
        
        # 等待审批结果
        result = await self._wait_for_approval(approval['id'])
        
        return {
            "passed": result['decision'] == 'approve',
            "score": 100 if result['decision'] == 'approve' else 0,
            "feedback": result.get('comment', ''),
            "details": {"approval_id": approval['id']}
        }
```

---

### 任务 4：进度追踪与恢复（第 13-15 天）

#### 3.4.1 进度管理器

```python
# B5-Loop引擎/src/loop/progress.py

class ProgressManager:
    """进度管理器"""
    
    def __init__(self, checkpoint_service):
        self.checkpoint_service = checkpoint_service
    
    async def save_progress(
        self,
        run_id: str,
        iteration: int,
        state: dict,
        usage: dict
    ) -> str:
        """保存进度"""
        checkpoint_data = {
            "graph_state": state,
            "node_state": {
                "current_node": f"iteration_{iteration}",
                "next_node": f"iteration_{iteration + 1}"
            },
            "context_digest": canonical_sha256(state),
            "side_effect_ledger": state.get('side_effects', []),
            "pending_approvals": state.get('pending_approvals', []),
            "pending_tool_calls": state.get('pending_tool_calls', []),
            "resume_token_ref": self._generate_resume_token(),
            "reason": "periodic"
        }
        
        checkpoint_id = await self.checkpoint_service.create_checkpoint(
            run_id=run_id,
            data=checkpoint_data
        )
        
        return checkpoint_id
    
    async def restore_progress(
        self,
        run_id: str,
        checkpoint_id: str = None
    ) -> dict:
        """恢复进度"""
        if checkpoint_id:
            checkpoint = await self.checkpoint_service.get_checkpoint(checkpoint_id)
        else:
            checkpoint = await self.checkpoint_service.get_latest_checkpoint(run_id)
        
        if not checkpoint:
            return None
        
        return {
            "state": checkpoint['graph_state'],
            "iteration": int(checkpoint['node_state']['current_node'].split('_')[1]),
            "side_effects": checkpoint['side_effect_ledger'],
            "checkpoint_id": checkpoint['id']
        }
```

---

## 四、关键知识点

### 4.1 Loop 与 Graph 的区别

| 特性 | Loop | Graph |
|---|---|---|
| 结构 | 线性迭代 | 复杂拓扑 |
| 分支 | 无 | 支持 |
| 并行 | 无 | 支持 |
| 适用 | 简单迭代 | 复杂工作流 |

### 4.2 预算控制

```python
# 每次迭代检查预算
if self._check_budget_exceeded():
    # 必须停止，不能静默超支
    return {"status": "budget_exceeded"}
```

### 4.3 硬停止条件

```python
# 所有 Loop 必须具有硬停止条件
stop_conditions = [
    {"condition_type": "success", "expression": "..."},
    {"condition_type": "failure", "expression": "..."},
    {"condition_type": "budget", "expression": "usage.cost_usd > max_cost"},
    {"condition_type": "human_stop", "expression": "user_requested_stop"}
]
```

---

## 五、验收标准

- [ ] 支持所有 Loop 策略类型
- [ ] 评估器可扩展
- [ ] 预算控制有效
- [ ] 进度可持久化和恢复
- [ ] 硬停止条件有效
- [ ] 单元测试覆盖率 > 80%

---

## 六、下一步

完成 B5 后，进入 B6 业务 Agent 开发。
