# B6 业务 Agent 开发指南

> 文档版本：1.0.0
> 创建日期：2026-09-01
> 前置依赖：B5 Loop 引擎
> 预计工期：4-6 周

---

## 一、B6 目标

基于 B0-B5 基础设施，实现电商生态的 3 个核心业务 Agent。

### 1.1 业务 Agent 列表

| Agent | 职责 | 主要能力 |
|---|---|---|
| 售前咨询 Agent | 商品售前客服 | RAG 检索、多模态回复 |
| 直播切片 Agent | 直播内容处理 | ASR 转写、视频剪辑 |
| 自媒体运营 Agent | 内容生成 | 图文生成、视频制作 |

## 二、售前咨询 Agent

### 2.1 Agent 定义

```json
{
  "api_version": "agent-platform/v1alpha1",
  "kind": "AgentSpec",
  "metadata": {
    "id": "agt_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
    "key": "presale-consultant",
    "namespace": "ecommerce",
    "version": "1.0.0",
    "revision": 1,
    "scope": {
      "type": "tenant",
      "tenant_id": "ten_ecommerce"
    }
  },
  "spec": {
    "purpose": "为电商平台用户提供商品售前咨询服务",
    "domain": "ecommerce",
    "goals": [
      "准确回答商品相关问题",
      "提供专业的购买建议",
      "解决用户疑虑，促进转化"
    ],
    "non_goals": [
      "处理售后问题",
      "进行价格谈判",
      "承诺无法兑现的优惠"
    ],
    "input_schema_ref": {
      "id": "sch_presale_input",
      "version": "1.0.0"
    },
    "output_schema_ref": {
      "id": "sch_presale_output",
      "version": "1.0.0"
    },
    "prompt_package_ref": {
      "kind": "PromptPackage",
      "id": "prm_presale_consultant",
      "version": "1.0.0"
    },
    "context_policy_ref": {
      "kind": "ContextPolicy",
      "id": "cpo_presale",
      "version": "1.0.0"
    },
    "model_policy_ref": {
      "kind": "ModelPolicy",
      "id": "mpo_presale",
      "version": "1.0.0"
    },
    "loop_profile_ref": {
      "kind": "LoopProfile",
      "id": "lop_single_pass",
      "version": "1.0.0"
    },
    "permission_profile_ref": {
      "kind": "PermissionProfile",
      "id": "pep_presale_readonly",
      "version": "1.0.0"
    },
    "skill_bindings": [
      {
        "selector": {
          "domain": "ecommerce",
          "status": "active"
        },
        "max_candidates": 5
      }
    ],
    "tool_bindings": [
      {
        "selector": {
          "domain": "rag"
        },
        "max_candidates": 3
      }
    ],
    "memory_policy": {
      "readable_scopes": ["user", "tenant"],
      "writable_scopes": ["user"],
      "write_requires_approval": false,
      "max_retention_days": 90,
      "allow_cross_user": false,
      "allow_cross_tenant": false
    },
    "budget_defaults": {
      "max_wall_time_seconds": 60,
      "max_model_tokens": 10000,
      "max_cost_usd": 0.1,
      "max_tool_calls": 5,
      "max_iterations": 3
    },
    "approval_defaults": {
      "external_send": false,
      "destructive": true,
      "privileged": true,
      "approval_ttl_seconds": 300
    },
    "concurrency_policy": {
      "max_parallel_tasks": 100,
      "max_parallel_runs_per_task": 1
    },
    "eval_suite_refs": []
  },
  "status": {
    "phase": "draft",
    "observed_revision": 1
  }
}
```

### 2.2 Prompt Package

```json
{
  "api_version": "agent-platform/v1alpha1",
  "kind": "PromptPackage",
  "metadata": {
    "id": "prm_presale_consultant",
    "key": "presale-consultant-prompt",
    "namespace": "ecommerce",
    "version": "1.0.0"
  },
  "spec": {
    "fragments": [
      {
        "name": "safety",
        "layer": "safety",
        "order": 0,
        "content": "你是一个专业的电商售前客服。请遵守以下安全规则：\n1. 不得泄露内部商业机密\n2. 不得承诺无法兑现的优惠\n3. 不得引导用户进行站外交易\n4. 敏感信息必须脱敏处理"
      },
      {
        "name": "identity",
        "layer": "identity",
        "order": 1,
        "content": "你是{brand_name}的官方AI客服助手，专门负责商品售前咨询服务。你具备丰富的商品知识，能够为用户提供专业、准确的购物建议。"
      },
      {
        "name": "domain",
        "layer": "domain",
        "order": 2,
        "content": "## 商品知识\n{rag_context}\n\n## 常见问题\n- 价格问题：引导查看商品详情页\n- 库存问题：查询实时库存系统\n- 配送问题：说明配送政策\n- 退换货：引导查看售后政策"
      },
      {
        "name": "behavior",
        "layer": "behavior",
        "order": 3,
        "content": "## 回复原则\n1. 先理解用户需求，再提供信息\n2. 回答要准确、专业、友好\n3. 涉及价格、库存等实时信息，必须查询系统\n4. 不确定的问题，建议联系人工客服\n5. 适当使用表情符号，增加亲和力"
      },
      {
        "name": "output_contract",
        "layer": "output_contract",
        "order": 4,
        "content": "## 输出格式\n请以 JSON 格式返回：\n```json\n{\n  \"reply\": \"回复内容\",\n  \"confidence\": 0.95,\n  \"need_human\": false,\n  \"suggested_actions\": [\"查看商品详情\", \"加入购物车\"]\n}\n```"
      }
    ],
    "variables_schema_ref": {
      "id": "sch_presale_variables",
      "version": "1.0.0"
    },
    "model_compatibility": {
      "required_capabilities": ["tool_calling", "structured_output"],
      "provider_allowlist": ["openai", "anthropic", "qwen"]
    },
    "output_schema_ref": {
      "id": "sch_presale_output",
      "version": "1.0.0"
    },
    "max_static_tokens": 2000,
    "eval_suite_refs": [],
    "change_summary": "初始版本"
  }
}
```

### 2.3 Context Policy

```json
{
  "api_version": "agent-platform/v1alpha1",
  "kind": "ContextPolicy",
  "metadata": {
    "id": "cpo_presale",
    "key": "presale-context-policy",
    "namespace": "ecommerce",
    "version": "1.0.0"
  },
  "spec": {
    "source_rules": [
      {
        "source": "task",
        "effect": "allow",
        "priority": 100
      },
      {
        "source": "agent_spec",
        "effect": "allow",
        "priority": 95
      },
      {
        "source": "prompt",
        "effect": "allow",
        "priority": 90
      },
      {
        "source": "rag_knowledge",
        "effect": "allow",
        "priority": 80
      },
      {
        "source": "memory",
        "effect": "allow",
        "priority": 60
      },
      {
        "source": "tool_schema",
        "effect": "allow",
        "priority": 70
      }
    ],
    "token_budget": {
      "total_tokens": 8000,
      "reserved_output_tokens": 2000,
      "per_source": {
        "task": 500,
        "agent_spec": 300,
        "prompt": 2000,
        "rag_knowledge": 3000,
        "memory": 500,
        "tool_schema": 500
      }
    },
    "skill_selection": {
      "top_k": 3,
      "similarity_threshold": 0.7,
      "metadata_token_limit": 500
    },
    "tool_selection": {
      "max_visible_tools": 5,
      "schema_token_limit": 1000
    },
    "memory_scope": {
      "allowed_scopes": ["user", "tenant"],
      "allow_cross_user": false,
      "allow_cross_tenant": false
    },
    "freshness": {
      "default_ttl_seconds": 3600
    },
    "deduplication": {
      "strategy": "digest"
    },
    "compaction": {
      "strategy": "extractive",
      "target_ratio": 0.7,
      "preserve_provenance": true
    },
    "redaction": {
      "redact_secrets": true,
      "pii_mode": "mask",
      "restricted_data_mode": "deny"
    },
    "provenance_requirement": true,
    "snapshot_policy": {
      "persist": true,
      "store_content": false,
      "retention_days": 30,
      "require_digest": true
    }
  }
}
```

### 2.4 实现代码

```python
# B6-业务Agent/售前咨询Agent/src/agent.py

from agent_platform_contracts.models import AgentRunResource

class PresaleConsultantAgent:
    """售前咨询 Agent"""
    
    def __init__(self, harness, rag_tool, product_service):
        self.harness = harness
        self.rag_tool = rag_tool
        self.product_service = product_service
    
    async def handle_consultation(self, user_message: str, context: dict) -> dict:
        """处理咨询请求"""
        # 1. 创建 Task
        task = await self._create_task(user_message, context)
        
        # 2. 创建 AgentRun
        run = await self._create_agent_run(task)
        
        # 3. 执行 Agent
        result = await self.harness.run_agent(
            run_id=run['id'],
            agent_spec=self.agent_spec,
            task=task,
            model_client=self.model_client
        )
        
        # 4. 解析结果
        response = self._parse_response(result)
        
        return response
    
    async def _create_task(self, user_message: str, context: dict) -> dict:
        """创建咨询任务"""
        return {
            "title": "用户售前咨询",
            "intent": "ecommerce.presale_consultation",
            "domain": "ecommerce",
            "requested_by": {
                "actor_type": "user",
                "actor_id": context['user_id']
            },
            "source": {
                "type": "openclaw",
                "channel": context.get('channel', 'web')
            },
            "payload": {
                "user_message": user_message,
                "product_id": context.get('product_id'),
                "conversation_history": context.get('history', [])
            },
            "input_schema_ref": {"id": "sch_presale_input", "version": "1.0.0"},
            "expected_output_schema_ref": {"id": "sch_presale_output", "version": "1.0.0"},
            "priority": 50,
            "budget": {
                "max_wall_time_seconds": 60,
                "max_model_tokens": 10000,
                "max_cost_usd": 0.1,
                "max_tool_calls": 5,
                "max_iterations": 3
            },
            "permission_grant": {
                "actions": ["rag.search", "product.query"],
                "resources": [f"product:{context.get('product_id', '*')}"]
            },
            "idempotency_key": f"presale:{context['user_id']}:{context.get('session_id')}"
        }
    
    def _parse_response(self, result: dict) -> dict:
        """解析 Agent 响应"""
        output = result.get('output', {})
        
        return {
            "reply": output.get('reply', '抱歉，我无法回答这个问题。'),
            "confidence": output.get('confidence', 0),
            "need_human": output.get('need_human', False),
            "suggested_actions": output.get('suggested_actions', [])
        }
```

---

## 三、直播切片 Agent

### 3.1 Agent 定义

```json
{
  "api_version": "agent-platform/v1alpha1",
  "kind": "AgentSpec",
  "metadata": {
    "id": "agt_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f412",
    "key": "live-clipper",
    "namespace": "ecommerce",
    "version": "1.0.0"
  },
  "spec": {
    "purpose": "对直播流进行智能切片，提取有价值的商品介绍片段",
    "domain": "ecommerce",
    "goals": [
      "自动识别直播中的商品介绍片段",
      "生成高质量的直播切片视频",
      "提取商品关键信息用于素材中心"
    ],
    "non_goals": [
      "处理完整的直播回放",
      "进行视频特效制作"
    ],
    "skill_bindings": [
      {
        "selector": {
          "domain": "video_processing",
          "status": "active"
        },
        "max_candidates": 5
      }
    ],
    "tool_bindings": [
      {
        "selector": {
          "domain": "asr"
        },
        "max_candidates": 2
      },
      {
        "selector": {
          "domain": "video"
        },
        "max_candidates": 3
      }
    ]
  }
}
```

### 3.2 切片流程 Skill

```json
{
  "api_version": "agent-platform/v1alpha1",
  "kind": "SkillManifest",
  "metadata": {
    "id": "skl_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f413",
    "key": "live-clip-workflow",
    "namespace": "ecommerce",
    "version": "1.0.0"
  },
  "spec": {
    "portable_name": "live-clip-workflow",
    "description": "直播切片完整工作流：ASR转写 → 内容分析 → 片段提取 → 视频剪辑",
    "domain": ["video_processing", "ecommerce"],
    "trigger_examples": {
      "positive": [
        "帮我把这段直播切成商品介绍片段",
        "从直播回放中提取商品讲解部分"
      ],
      "negative": [
        "帮我剪辑一个短视频",
        "给视频加字幕"
      ]
    },
    "required_tools": [
      {
        "tool_ref": {
          "kind": "ToolManifest",
          "id": "tol_asr_service",
          "version": "1.0.0"
        },
        "required_capabilities": ["speech_to_text"]
      },
      {
        "tool_ref": {
          "kind": "ToolManifest",
          "id": "tol_video_editor",
          "version": "1.0.0"
        },
        "required_capabilities": ["video_cut", "video_merge"]
      }
    ],
    "risk_level": "medium",
    "runtime_requirements": {
      "operating_systems": ["linux"],
      "binaries": ["ffmpeg"],
      "network_domains": [],
      "has_scripts": true,
      "sandbox_required": true,
      "sandbox_profile": "video_processing"
    },
    "context_budget": {
      "max_skill_tokens": 5000,
      "max_reference_tokens": 10000,
      "max_total_tokens": 15000
    }
  }
}
```

### 3.3 实现代码

```python
# B6-业务Agent/直播切片Agent/src/agent.py

class LiveClipperAgent:
    """直播切片 Agent"""
    
    def __init__(self, harness, asr_tool, video_editor_tool, content_analyzer):
        self.harness = harness
        self.asr = asr_tool
        self.video_editor = video_editor_tool
        self.analyzer = content_analyzer
    
    async def process_live_stream(self, video_url: str, config: dict) -> dict:
        """处理直播流"""
        # 1. ASR 转写
        transcript = await self.asr.transcribe(
            audio_url=video_url,
            language=config.get('language', 'zh-CN')
        )
        
        # 2. 内容分析
        segments = await self.analyzer.extract_product_segments(
            transcript=transcript,
            min_duration=config.get('min_clip_duration', 30),
            max_duration=config.get('max_clip_duration', 180)
        )
        
        # 3. 生成切片
        clips = []
        for segment in segments:
            clip = await self.video_editor.cut(
                video_url=video_url,
                start_time=segment['start_time'],
                end_time=segment['end_time'],
                output_format='mp4'
            )
            clips.append({
                "clip_id": clip['id'],
                "product_info": segment['product_info'],
                "duration": segment['duration'],
                "url": clip['url']
            })
        
        # 4. 输出到素材中心
        await self._export_to_asset_center(clips)
        
        return {
            "total_clips": len(clips),
            "clips": clips,
            "transcript": transcript
        }
```

---

## 四、自媒体运营 Agent

### 4.1 Agent 定义

```json
{
  "api_version": "agent-platform/v1alpha1",
  "kind": "AgentSpec",
  "metadata": {
    "id": "agt_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f414",
    "key": "content-creator",
    "namespace": "ecommerce",
    "version": "1.0.0"
  },
  "spec": {
    "purpose": "自动生成电商营销内容，包括图文、短视频脚本",
    "domain": "ecommerce",
    "goals": [
      "生成高质量的商品营销文案",
      "创作短视频脚本和分镜",
      "适配不同平台的内容风格"
    ],
    "non_goals": [
      "直接发布内容到外部平台",
      "进行内容审核"
    ],
    "skill_bindings": [
      {
        "selector": {
          "domain": "content_generation",
          "status": "active"
        },
        "max_candidates": 8
      }
    ],
    "tool_bindings": [
      {
        "selector": {
          "domain": "image_generation"
        },
        "max_candidates": 2
      },
      {
        "selector": {
          "domain": "text_generation"
        },
        "max_candidates": 3
      }
    ]
  }
}
```

### 4.2 内容生成 Skill

```json
{
  "api_version": "agent-platform/v1alpha1",
  "kind": "SkillManifest",
  "metadata": {
    "id": "skl_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f415",
    "key": "content-generation-workflow",
    "namespace": "ecommerce",
    "version": "1.0.0"
  },
  "spec": {
    "portable_name": "content-generation-workflow",
    "description": "内容生成工作流：需求分析 → 内容策划 → 文案创作 → 素材生成 → 质量评估",
    "domain": ["content_generation", "ecommerce"],
    "trigger_examples": {
      "positive": [
        "帮我写一个商品推广文案",
        "生成一个短视频脚本"
      ],
      "negative": [
        "翻译这段文字",
        "总结这篇文章"
      ]
    },
    "required_tools": [
      {
        "tool_ref": {
          "kind": "ToolManifest",
          "id": "tol_image_generator",
          "version": "1.0.0"
        },
        "required_capabilities": ["text_to_image"]
      }
    ],
    "risk_level": "low",
    "runtime_requirements": {
      "operating_systems": ["any"],
      "binaries": [],
      "network_domains": [],
      "has_scripts": false,
      "sandbox_required": false
    },
    "context_budget": {
      "max_skill_tokens": 8000,
      "max_reference_tokens": 5000,
      "max_total_tokens": 13000
    }
  }
}
```

### 4.3 实现代码

```python
# B6-业务Agent/自媒体运营Agent/src/agent.py

class ContentCreatorAgent:
    """自媒体运营 Agent"""
    
    def __init__(self, harness, image_generator, copywriter):
        self.harness = harness
        self.image_gen = image_generator
        self.copywriter = copywriter
    
    async def create_content(self, brief: dict) -> dict:
        """创建营销内容"""
        # 1. 分析需求
        analysis = await self._analyze_brief(brief)
        
        # 2. 生成文案
        copy = await self.copywriter.generate(
            product_info=analysis['product_info'],
            platform=brief['platform'],
            style=brief.get('style', 'professional'),
            length=brief.get('length', 'medium')
        )
        
        # 3. 生成配图
        images = []
        if brief.get('need_images', True):
            for image_prompt in copy.get('image_prompts', []):
                image = await self.image_gen.generate(
                    prompt=image_prompt,
                    style=brief.get('image_style', 'product')
                )
                images.append(image)
        
        # 4. 输出到素材中心
        content_package = {
            "text": copy['text'],
            "images": images,
            "metadata": {
                "platform": brief['platform'],
                "product_id": brief['product_id'],
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        }
        
        await self._export_to_asset_center(content_package)
        
        return content_package
    
    async def _analyze_brief(self, brief: dict) -> dict:
        """分析内容需求"""
        # 获取商品信息
        product_info = await self.product_service.get_product(brief['product_id'])
        
        # 分析目标受众
        audience = brief.get('target_audience', 'general')
        
        return {
            "product_info": product_info,
            "audience": audience,
            "platform": brief['platform'],
            "tone": brief.get('tone', 'professional')
        }
```

---

## 五、Tool 注册

### 5.1 RAG 检索 Tool

```json
{
  "api_version": "agent-platform/v1alpha1",
  "kind": "ToolManifest",
  "metadata": {
    "id": "tol_rag_search",
    "key": "rag-search",
    "namespace": "ecommerce",
    "version": "1.0.0"
  },
  "spec": {
    "provider": "rag_service",
    "capability": "knowledge_search",
    "domain": ["rag", "ecommerce"],
    "transport": "http",
    "endpoint_ref": {
      "service_id": "rag_service",
      "endpoint_key": "/api/v1/search"
    },
    "input_schema_ref": {
      "id": "sch_rag_input",
      "version": "1.0.0"
    },
    "output_schema_ref": {
      "id": "sch_rag_output",
      "version": "1.0.0"
    },
    "side_effect": "read_only",
    "risk_level": "low",
    "idempotency": {
      "supported": true,
      "key_scope": "tool_target",
      "duplicate_semantics": "return_original"
    },
    "timeout_policy": {
      "connect_timeout_seconds": 5,
      "execution_timeout_seconds": 30
    },
    "retry_policy": {
      "max_attempts": 3,
      "retryable_error_codes": ["TIMEOUT", "RATE_LIMITED"],
      "backoff": "exponential",
      "base_delay_seconds": 1,
      "requires_safe_to_retry": true
    },
    "execution_location": "cloud",
    "approval_requirement": {
      "mode": "none",
      "conditions": []
    },
    "health_contract": {
      "healthcheck_key": "rag_service_health",
      "interval_seconds": 30,
      "unhealthy_after_failures": 3
    }
  }
}
```

### 5.2 ASR 转写 Tool

```json
{
  "api_version": "agent-platform/v1alpha1",
  "kind": "ToolManifest",
  "metadata": {
    "id": "tol_asr_service",
    "key": "asr-transcription",
    "namespace": "ecommerce",
    "version": "1.0.0"
  },
  "spec": {
    "provider": "asr_service",
    "capability": "speech_to_text",
    "domain": ["asr", "video_processing"],
    "transport": "http",
    "endpoint_ref": {
      "service_id": "asr_service",
      "endpoint_key": "/api/v1/transcribe"
    },
    "side_effect": "read_only",
    "risk_level": "low",
    "idempotency": {
      "supported": true,
      "key_scope": "tool_target",
      "duplicate_semantics": "return_original"
    },
    "timeout_policy": {
      "connect_timeout_seconds": 10,
      "execution_timeout_seconds": 300
    },
    "execution_location": "cloud"
  }
}
```

---

## 六、关键知识点

### 6.1 Agent 与 Skill 的关系

```
Agent (AgentSpec)
    │
    ├── 绑定多个 Skill
    │   ├── Skill A (直播切片流程)
    │   ├── Skill B (内容生成流程)
    │   └── Skill C (数据分析流程)
    │
    └── 绑定多个 Tool
        ├── Tool 1 (RAG 检索)
        ├── Tool 2 (ASR 转写)
        └── Tool 3 (视频剪辑)
```

### 6.2 Skill 触发机制

```python
# Skill 通过 trigger_examples 匹配
trigger_examples = {
    "positive": ["帮我切片直播"],  # 应该触发
    "negative": ["帮我剪辑视频"]   # 不应该触发
}

# 匹配逻辑
async def should_trigger_skill(skill, user_message):
    # 使用模型判断是否匹配
    return await model.evaluate_similarity(
        user_message, 
        skill.trigger_examples.positive
    ) > threshold
```

### 6.3 数据闭环

```
业务 Agent 运行
    │
    ▼
产生运行数据（Event）
    │
    ▼
数据中台收集
    │
    ▼
数据清洗导出
    │
    ├──→ RAG 知识库更新
    ├──→ 模型微调数据
    └──→ 素材中心补充
```

---

## 七、验收标准

- [ ] 3 个业务 Agent 可正常运行
- [ ] Agent 可正确触发相关 Skill
- [ ] Tool 调用符合权限控制
- [ ] 数据闭环回流正常
- [ ] 性能满足业务需求
- [ ] 单元测试覆盖率 > 80%

---

## 八、项目完成

完成 B6 后，整个电商 AI Agent 生态系统的基础架构和核心业务 Agent 就开发完成了。后续可以：

1. 扩展更多业务 Agent
2. 优化现有 Agent 性能
3. 完善数据闭环
4. 接入更多外部系统
