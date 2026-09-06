# B4 Agent 执行器（Harness）开发指南

> 文档版本：1.0.0
> 创建日期：2026-09-01
> 前置依赖：B3 Context 引擎
> 预计工期：4-5 周

---

## 一、B4 目标

实现 Agent Harness，即 Agent 的运行时执行环境，负责权限控制、Tool 调用、审批流程和沙箱隔离。

### 1.1 核心职责

- 权限决策引擎
- Tool 调用生命周期管理
- 审批流程集成
- 沙箱执行环境
- 审计日志记录

### 1.2 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Harness                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  Permission Engine                       │    │
│  │  ┌──────────────────────────────────────────────┐       │    │
│  │  │ RBAC + ABAC + Capability + Deny Priority     │       │    │
│  │  └──────────────────────────────────────────────┘       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                     │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  Tool Executor                           │    │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                      │    │
│  │  │ MCP │ │ HTTP│ │ GRPC│ │Local│                      │    │
│  │  └─────┘ └─────┘ └─────┘ └─────┘                      │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                     │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  Approval Flow                           │    │
│  │  ┌──────────────────────────────────────────────┐       │    │
│  │  │ Request → Approve/Reject → Execute/Cancel    │       │    │
│  │  └──────────────────────────────────────────────┘       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                     │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  Sandbox Manager                         │    │
│  │  ┌──────────────────────────────────────────────┐       │    │
│  │  │ Docker / Process Isolation / Resource Limits  │       │    │
│  │  └──────────────────────────────────────────────┘       │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## 二、开发任务分解

### 任务 1：权限决策引擎（第 1-5 天）

#### 2.1.1 权限请求与决策

```python
# B4-Agent执行器/src/harness/permission/engine.py

from dataclasses import dataclass
from typing import List, Optional

@dataclass
class PermissionRequest:
    """权限请求"""
    actor: dict           # ActorRef
    user_ref: str
    tenant_ref: str
    task_ref: str
    run_ref: str
    action: str           # 如 "repository.write"
    resource: str         # 如 "project:prj_demo/repository:main"
    tool_ref: Optional[dict] = None
    skill_ref: Optional[dict] = None
    environment: str = "development"
    input_digest: Optional[str] = None
    risk_level: str = "low"

@dataclass
class PermissionDecision:
    """权限决策"""
    decision: str         # allow / deny / require_approval
    policy_refs: List[dict]
    reason_codes: List[str]
    constraints: dict
    request_digest: str
    decision_digest: str

class PermissionEngine:
    """权限决策引擎"""
    
    def __init__(self, registry_service, policy_cache):
        self.registry = registry_service
        self.cache = policy_cache
    
    async def evaluate(self, request: PermissionRequest) -> PermissionDecision:
        """评估权限请求"""
        # 1. 收集所有相关策略
        policies = await self._collect_policies(request)
        
        # 2. 计算交集权限
        decisions = []
        for policy in policies:
            decision = self._evaluate_single_policy(policy, request)
            decisions.append(decision)
        
        # 3. 应用 Deny 优先规则
        final_decision = self._combine_decisions(decisions)
        
        # 4. 计算约束条件
        constraints = self._compute_constraints(policies, request)
        
        # 5. 生成决策摘要
        request_digest = canonical_sha256(request.__dict__)
        decision_digest = canonical_sha256({
            "decision": final_decision,
            "request_digest": request_digest
        })
        
        return PermissionDecision(
            decision=final_decision,
            policy_refs=[p['id'] for p in policies],
            reason_codes=self._get_reason_codes(decisions),
            constraints=constraints,
            request_digest=request_digest,
            decision_digest=decision_digest
        )
    
    async def _collect_policies(self, request: PermissionRequest) -> List[dict]:
        """收集所有相关策略"""
        policies = []
        
        # 1. 租户策略
        tenant_policy = await self._get_tenant_policy(request.tenant_ref)
        if tenant_policy:
            policies.append(tenant_policy)
        
        # 2. 用户策略
        user_policy = await self._get_user_policy(request.user_ref)
        if user_policy:
            policies.append(user_policy)
        
        # 3. Agent 策略
        if request.run_ref:
            run = await self._get_run(request.run_ref)
            agent_snapshot = run.get('agent_snapshot', {})
            agent_policy = await self._get_agent_policy(agent_snapshot.get('id'))
            if agent_policy:
                policies.append(agent_policy)
        
        # 4. Skill 策略
        if request.skill_ref:
            skill_policy = await self._get_skill_policy(request.skill_ref['id'])
            if skill_policy:
                policies.append(skill_policy)
        
        # 5. Task 策略
        if request.task_ref:
            task = await self._get_task(request.task_ref)
            task_policy = task.get('permission_grant')
            if task_policy:
                policies.append(task_policy)
        
        # 6. 环境策略
        env_policy = await self._get_environment_policy(request.environment)
        if env_policy:
            policies.append(env_policy)
        
        return policies
    
    def _evaluate_single_policy(self, policy: dict, request: PermissionRequest) -> str:
        """评估单个策略"""
        for rule in policy.get('rules', []):
            if self._rule_matches(rule, request):
                return rule['effect']
        return policy.get('default_decision', 'deny')
    
    def _rule_matches(self, rule: dict, request: PermissionRequest) -> bool:
        """检查规则是否匹配"""
        # 检查 action
        if not self._action_matches(rule['actions'], request.action):
            return False
        
        # 检查 resource
        if not self._resource_matches(rule['resources'], request.resource):
            return False
        
        # 检查 conditions
        if not self._conditions_match(rule.get('conditions', {}), request):
            return False
        
        return True
    
    def _combine_decisions(self, decisions: List[str]) -> str:
        """合并多个决策（Deny 优先）"""
        from agent_platform_contracts.policies import combine_permission_decisions
        return combine_permission_decisions(decisions)
```

**学习要点**：
- 权限决策是多层策略的交集
- Deny 始终优先于 Allow
- 决策必须可审计和复现

---

### 任务 2：Tool 调用执行器（第 6-10 天）

#### 2.2.1 Tool Executor

```python
# B4-Agent执行器/src/harness/tool/executor.py

from typing import Optional
from datetime import datetime, timezone

class ToolCallExecutor:
    """Tool 调用执行器"""
    
    def __init__(
        self, 
        permission_engine: PermissionEngine,
        approval_service,
        sandbox_manager,
        event_store
    ):
        self.permission = permission_engine
        self.approval = approval_service
        self.sandbox = sandbox_manager
        self.events = event_store
    
    async def execute_tool_call(
        self, 
        run_id: str, 
        tool_ref: dict, 
        input_data: dict,
        requested_by: dict
    ) -> dict:
        """执行 Tool 调用"""
        # 1. 获取 Tool 定义
        tool = await self.registry.get_definition(tool_ref['id'])
        
        # 2. 创建 ToolCall 记录
        tool_call = await self._create_tool_call(
            run_id=run_id,
            tool=tool,
            input_data=input_data,
            requested_by=requested_by
        )
        
        # 3. Schema 验证
        await self._validate_input(tool, input_data)
        
        # 4. 权限检查
        permission_decision = await self._check_permission(tool_call, tool)
        
        if permission_decision.decision == 'deny':
            await self._update_status(tool_call['id'], 'denied')
            raise PermissionError(f"Tool call denied: {permission_decision.reason_codes}")
        
        # 5. 审批检查
        if permission_decision.decision == 'require_approval' or \
           self._requires_approval(tool, input_data):
            
            approval = await self._request_approval(tool_call, tool, input_data)
            
            if approval['status'] == 'rejected':
                await self._update_status(tool_call['id'], 'rejected')
                raise PermissionError("Tool call rejected by approver")
            
            if approval['status'] == 'expired':
                await self._update_status(tool_call['id'], 'expired')
                raise TimeoutError("Approval expired")
        
        # 6. 执行
        try:
            result = await self._do_execute(tool_call, tool, input_data)
            
            # 7. 保存副作用回执
            if tool['spec']['side_effect'] != 'read_only':
                await self._save_side_effect_receipt(tool_call, result)
            
            # 8. 更新状态
            await self._update_status(tool_call['id'], 'succeeded')
            
            return {
                "tool_call_id": tool_call['id'],
                "status": "succeeded",
                "output": result
            }
            
        except Exception as e:
            # 9. 处理失败
            error = self._create_error(e)
            await self._update_status(tool_call['id'], 'failed', error=error)
            
            # 10. 检查是否可重试
            if self._can_retry(tool, e, tool_call):
                return await self._retry(tool_call, tool, input_data)
            
            raise
    
    async def _do_execute(self, tool_call: dict, tool: dict, input_data: dict) -> dict:
        """实际执行 Tool"""
        transport = tool['spec']['transport']
        
        if transport == 'mcp':
            return await self._execute_mcp(tool, input_data)
        elif transport == 'http':
            return await self._execute_http(tool, input_data)
        elif transport == 'grpc':
            return await self._execute_grpc(tool, input_data)
        elif transport == 'local':
            return await self._execute_local(tool, input_data)
        else:
            raise ValueError(f"Unsupported transport: {transport}")
    
    async def _execute_mcp(self, tool: dict, input_data: dict) -> dict:
        """通过 MCP 协议执行"""
        endpoint = tool['spec']['endpoint_ref']
        
        # 调用 MCP Server
        result = await self.mcp_client.call(
            server_id=endpoint['service_id'],
            tool=endpoint['endpoint_key'],
            arguments=input_data
        )
        
        return result
    
    async def _execute_http(self, tool: dict, input_data: dict) -> dict:
        """通过 HTTP 执行"""
        endpoint = tool['spec']['endpoint_ref']
        
        # 解析认证信息
        auth = await self._resolve_auth(tool.get('auth_profile_ref'))
        
        # 发送请求
        async with httpx.AsyncClient() as client:
            response = await client.post(
                endpoint['url'],
                json=input_data,
                headers=auth,
                timeout=tool['spec']['timeout_policy']['execution_timeout_seconds']
            )
            
            return response.json()
    
    async def _execute_local(self, tool: dict, input_data: dict) -> dict:
        """在沙箱中本地执行"""
        # 获取沙箱配置
        sandbox_profile = tool['spec'].get('sandbox_profile')
        
        # 在沙箱中执行
        result = await self.sandbox.execute(
            profile=sandbox_profile,
            code=tool['spec'].get('executable_code'),
            input_data=input_data,
            timeout=tool['spec']['timeout_policy']['execution_timeout_seconds']
        )
        
        return result
    
    def _requires_approval(self, tool: dict, input_data: dict) -> bool:
        """检查是否需要审批"""
        approval_req = tool['spec']['approval_requirement']
        
        if approval_req['mode'] == 'always':
            return True
        
        if approval_req['mode'] == 'conditional':
            # 检查条件
            for condition in approval_req.get('conditions', []):
                if self._check_condition(condition, input_data):
                    return True
        
        return False
    
    def _can_retry(self, tool: dict, error: Exception, tool_call: dict) -> bool:
        """检查是否可以重试"""
        from agent_platform_contracts.policies import can_auto_retry
        
        return can_auto_retry(
            retryable=self._is_retryable(error),
            safe_to_retry=tool['spec']['idempotency']['supported'],
            tool_allows_retry=tool['spec']['retry_policy']['max_attempts'] > 1,
            state=tool_call['status']['phase']
        )
```

**学习要点**：
- Tool 执行必须经过权限和审批检查
- 副作用操作必须保存回执
- 重试必须满足幂等条件

---

### 任务 3：审批流程服务（第 11-14 天）

#### 2.3.1 Approval Service

```python
# B4-Agent执行器/src/harness/approval/service.py

from datetime import datetime, timedelta, timezone

class ApprovalService:
    """审批服务"""
    
    def __init__(self, approval_repo, notification_service):
        self.repo = approval_repo
        self.notifier = notification_service
    
    async def request_approval(
        self,
        subject_ref: dict,
        requester: dict,
        approval_type: str,
        risk_summary: str,
        requested_actions: list,
        input_digest: str,
        policy_snapshot: dict,
        required_approvers: list,
        ttl_seconds: int = 3600,
        one_time: bool = True
    ) -> dict:
        """创建审批请求"""
        approval = {
            "subject_ref": subject_ref,
            "requester": requester,
            "approval_type": approval_type,
            "risk_summary": risk_summary,
            "requested_actions": requested_actions,
            "input_digest": input_digest,
            "policy_snapshot": policy_snapshot,
            "required_approvers": required_approvers,
            "decisions": [],
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat(),
            "one_time": one_time,
            "usage_count": 0,
            "status": {"phase": "requested"}
        }
        
        approval_id = await self.repo.create_approval(approval)
        
        # 通知审批人
        await self._notify_approvers(approval_id, required_approvers)
        
        return {"id": approval_id, "phase": "requested"}
    
    async def approve(
        self, 
        approval_id: str, 
        approver_id: str,
        comment: str = None
    ) -> dict:
        """审批通过"""
        approval = await self.repo.get_approval(approval_id)
        
        # 验证审批人资格
        if not self._is_valid_approver(approval, approver_id):
            raise ValueError("Invalid approver")
        
        # 检查是否过期
        if datetime.now(timezone.utc) > datetime.fromisoformat(approval['expires_at']):
            await self._update_status(approval_id, 'expired')
            raise ValueError("Approval expired")
        
        # 记录决策
        decision = {
            "approver": {"actor_type": "user", "actor_id": approver_id},
            "decision": "approve",
            "decided_at": datetime.now(timezone.utc).isoformat(),
            "comment": comment
        }
        approval['decisions'].append(decision)
        
        # 检查是否满足所有审批人要求
        if self._meets_approval_requirements(approval):
            await self._update_status(approval_id, 'approved')
            return {"id": approval_id, "phase": "approved"}
        
        await self.repo.save_approval(approval)
        return {"id": approval_id, "phase": "pending"}
    
    async def reject(
        self, 
        approval_id: str, 
        approver_id: str,
        reason: str
    ) -> dict:
        """审批拒绝"""
        approval = await self.repo.get_approval(approval_id)
        
        decision = {
            "approver": {"actor_type": "user", "actor_id": approver_id},
            "decision": "reject",
            "decided_at": datetime.now(timezone.utc).isoformat(),
            "comment": reason
        }
        approval['decisions'].append(decision)
        
        await self._update_status(approval_id, 'rejected')
        
        return {"id": approval_id, "phase": "rejected"}
    
    async def consume(self, approval_id: str) -> dict:
        """消费审批（用于一次性审批）"""
        approval = await self.repo.get_approval(approval_id)
        
        if approval['status']['phase'] != 'approved':
            raise ValueError("Approval not in approved state")
        
        if approval['one_time']:
            approval['usage_count'] += 1
            
            if approval['usage_count'] > 1:
                raise ValueError("One-time approval already consumed")
            
            await self._update_status(approval_id, 'consumed')
        
        return {"id": approval_id, "phase": approval['status']['phase']}
    
    def _meets_approval_requirements(self, approval: dict) -> bool:
        """检查是否满足审批要求"""
        required = approval['required_approvers']
        decisions = approval['decisions']
        
        for rule in required:
            role = rule['role']
            count = rule['count']
            
            # 计算该角色的审批数
            approvals = [
                d for d in decisions 
                if d['decision'] == 'approve' and 
                   d['approver'].get('role') == role
            ]
            
            if len(approvals) < count:
                return False
        
        return True
```

---

### 任务 4：沙箱管理器（第 15-18 天）

#### 2.4.1 Sandbox Manager

```python
# B4-Agent执行器/src/harness/sandbox/manager.py

import docker
from typing import Optional

class SandboxManager:
    """沙箱管理器"""
    
    def __init__(self, config: dict):
        self.config = config
        self.docker_client = docker.from_env()
    
    async def execute(
        self,
        profile: str,
        code: str,
        input_data: dict,
        timeout: int = 60
    ) -> dict:
        """在沙箱中执行代码"""
        # 1. 获取沙箱配置
        sandbox_config = self._get_sandbox_config(profile)
        
        # 2. 创建容器
        container = self.docker_client.containers.run(
            image=sandbox_config['image'],
            command=self._build_command(code, input_data),
            detach=True,
            network_mode='none' if not sandbox_config.get('network_access') else 'bridge',
            mem_limit=sandbox_config.get('memory_limit', '512m'),
            cpu_period=100000,
            cpu_quota=sandbox_config.get('cpu_quota', 50000),
            volumes=sandbox_config.get('volumes', {}),
            environment=sandbox_config.get('environment', {})
        )
        
        try:
            # 3. 等待执行完成
            result = container.wait(timeout=timeout)
            
            # 4. 获取输出
            logs = container.logs().decode('utf-8')
            
            if result['StatusCode'] == 0:
                return {
                    "status": "success",
                    "output": logs
                }
            else:
                return {
                    "status": "error",
                    "error": logs
                }
                
        except docker.errors.ContainerError as e:
            return {
                "status": "error",
                "error": str(e)
            }
        finally:
            # 5. 清理容器
            container.remove(force=True)
    
    def _get_sandbox_config(self, profile: str) -> dict:
        """获取沙箱配置"""
        profiles = self.config.get('profiles', {})
        
        if profile not in profiles:
            raise ValueError(f"Unknown sandbox profile: {profile}")
        
        return profiles[profile]
    
    def _build_command(self, code: str, input_data: dict) -> str:
        """构建执行命令"""
        import json
        input_json = json.dumps(input_data)
        return f"python -c '{code}' --input '{input_json}'"
```

**学习要点**：
- 沙箱隔离防止恶意代码影响宿主机
- 资源限制防止资源耗尽攻击
- 网络隔离防止未授权访问

---

### 任务 5：Harness 集成（第 19-22 天）

#### 2.5.1 Harness 主类

```python
# B4-Agent执行器/src/harness/harness.py

class AgentHarness:
    """Agent 执行器主类"""
    
    def __init__(
        self,
        context_engine: ContextEngine,
        permission_engine: PermissionEngine,
        tool_executor: ToolCallExecutor,
        approval_service: ApprovalService,
        sandbox_manager: SandboxManager,
        event_store: EventStore
    ):
        self.context = context_engine
        self.permission = permission_engine
        self.tool_executor = tool_executor
        self.approval = approval_service
        self.sandbox = sandbox_manager
        self.events = event_store
    
    async def run_agent(
        self,
        run_id: str,
        agent_spec: dict,
        task: dict,
        model_client
    ) -> dict:
        """执行 Agent"""
        # 1. 构建运行上下文
        run_context = self._build_run_context(run_id, agent_spec, task)
        
        # 2. 获取租约
        lease = await self._acquire_lease(run_id)
        
        # 3. 循环执行
        iteration = 0
        max_iterations = agent_spec['spec']['loop_profile_ref']['max_iterations']
        
        while iteration < max_iterations:
            iteration += 1
            
            # 4. 构建 Context
            context_package = await self.context.build_context(run_context)
            
            # 5. 调用模型
            model_response = await model_client.call(
                context=context_package,
                model_config=agent_spec['spec']['model_policy_ref']
            )
            
            # 6. 解析模型输出
            parsed = self._parse_model_output(model_response)
            
            # 7. 检查是否需要调用 Tool
            if parsed.get('tool_calls'):
                for tool_call in parsed['tool_calls']:
                    result = await self.tool_executor.execute_tool_call(
                        run_id=run_id,
                        tool_ref=tool_call['tool_ref'],
                        input_data=tool_call['input'],
                        requested_by={"actor_type": "agent", "actor_id": run_id}
                    )
                    # 将结果加入下一轮 Context
                    run_context['tool_results'] = run_context.get('tool_results', [])
                    run_context['tool_results'].append(result)
            
            # 8. 检查是否完成
            if parsed.get('is_complete'):
                break
            
            # 9. 创建 Checkpoint
            await self._create_checkpoint(run_id, iteration, context_package)
        
        # 10. 返回结果
        return {
            "run_id": run_id,
            "iterations": iteration,
            "output": parsed.get('final_output')
        }
```

---

## 三、关键知识点

### 3.1 权限决策流程

```python
# 权限决策是多层策略的交集
final_decision = combine_permission_decisions([
    tenant_decision,    # 租户策略
    user_decision,      # 用户策略
    agent_decision,     # Agent 策略
    skill_decision,     # Skill 策略
    task_decision,      # Task 策略
    env_decision        # 环境策略
])
# 任何一层 deny，最终结果就是 deny
```

### 3.2 审批流程

```
Tool Call 提出
    │
    ▼
权限检查 ──→ deny ──→ 拒绝执行
    │
    ▼
require_approval ──→ 创建 Approval 请求
    │
    ▼
等待审批 ──→ 超时 ──→ 过期
    │
    ▼
审批通过 ──→ 执行 Tool
    │
    ▼
保存副作用回执
```

### 3.3 沙箱隔离级别

| 隔离级别 | 描述 | 适用场景 |
|---|---|---|
| `none` | 无隔离 | 可信本地代码 |
| `process` | 进程隔离 | 一般 Skill 脚本 |
| `container` | Docker 容器隔离 | 不可信外部代码 |
| `vm` | 虚拟机隔离 | 高风险操作 |

---

## 四、验收标准

- [ ] 权限决策符合 Deny 优先原则
- [ ] Tool 调用经过完整权限检查
- [ ] 审批流程支持多级审批
- [ ] 沙箱执行环境隔离有效
- [ ] 副作用操作保存回执
- [ ] 审计日志完整
- [ ] 单元测试覆盖率 > 80%

---

## 五、下一步

完成 B4 后，进入 B5 Loop 引擎开发。
