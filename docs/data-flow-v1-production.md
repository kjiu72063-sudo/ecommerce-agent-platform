# V1 售前商品问答 —— 生产化数据流

> 配套：docs/architecture-v1-production.md
> 更新时间：2026-09-08
> 说明：描述端口化后一次问答、处置和到期的数据流；体现依赖方向与持久化端口。

## 1. 参与模块

```text
presale.contracts   业务对象模型（ProductQuestion/AnswerDraft/EvidenceRef）
presale.knowledge   知识检索（可替换：确定性/真实适配器）
presale.context      ContextPackage 组装（委托 B3）
presale.answer       回答生成（可替换：模板/真实模型适配器）
presale.disposition  人工处置规则
presale.runner       应用门面（依赖注入各端口）
presale.trace        运行追溯 + 保留策略
presale.retention    RetentionService（可选独立模块）
  ports/             端口接口（见架构文档 §5）
  adapters/          InMemory / Sqlite 适配器
```

## 2. 端口

```text
ProductQuestionRepository.save/get/find_by_idempotency
EvidenceRepository.save_evidence/get_by_run
AnswerDraftRepository.save/get_by_run
DispositionRepository.save/get_by_answer
RunTraceRepository.save/get/mark_archived/mark_disposition
```

所有端口操作必须携带 `tenant_id` 并校验租户边界；调用方通过端口接口使用，不依赖具体适配器。

## 3. 一次问答数据流

```text
调用方
  │  question(tenant, product, question_text, idempotency_key)
  ▼
PresaleQaRunner.ask(question)
  │  1. 幂等检查（find_by_idempotency）
  │     ├─ 命中 → 返回既有 run/result
  │     └─ 未命中 → 继续
  │  2. question_repo.save(question)          # 持久化业务请求
  ▼
knowledge retriever.retrieve(question)
  │  → RetrievalResult(status, evidence_items)
  │  evidence_repo.save_evidence(run_ref, items)
  ▼
presale.context build(question, evidence, refs)
  │  → ContextPackage（经 B0 校验）
  │  trace.mark_stage("context_built")
  ▼
answer generator.generate(question, retrieval, refs)
  │  → AnswerDraft（带证据或 need_human）
  │  answer_repo.save(draft)
  │  trace.mark_stage("answer_generated")
  ▼
trace_repo.save(trace)
  │  trace.mark_disposition(未处置 → PENDING)
  ▼
返回 PresaleQaResult(run_ref, answer_draft, trace)
```

## 4. 处置数据流

```text
调用方
  │  accept / edit / escalate / discard(answer_id, actor, reason)
  ▼
PresaleQaRunner.<disposition>
  │  disposition_repo.save(HumanDispositionRecord)
  │  trace_repo.mark_disposition(run_ref, COMPLETE 或 ESCALATED)
  ▼
返回 HumanDispositionRecord
```

- `accept/edit/discard` → `COMPLETE`
- `escalate` → `ESCALATED`
- 都不触发消费者发送；`sent_to_consumer=False` 保持。

## 5. 到期保留数据流

```text
RetentionService.archive_expired(tenant, now)
  │  逐条评估 RunTrace
  │    - disposition_state == COMPLETE 且超过保留期 → 标记归档
  │    - PENDING / ESCALATED → 跳过（不误删）
  ▼
trace_repo.mark_archived(run_ref, tenant)   # 软归档，保留 stages/Event/provenance 留痕
  ▼
返回已归档 run_ref 列表
```

不物理删除；历史事实语义不被改写。

## 6. 查询数据流

```text
调用方
  │  get_trace(run_ref, tenant)
  ▼
PresaleQaRunner.get_trace → RunTraceRepository.get(run_ref, tenant)
  │  校验 tenant 一致
  ▼
返回 PresaleRunTrace（含 stages / context / answer / disposition_state / archived）
```

跨租户或缺失租户 → `OUT_OF_SCOPE` / `TENANT_ID_REQUIRED`。

## 7. 依赖方向

```text
调用方 / CLI
  │
  ▼
presale.runner（应用门面）
  ├── port 接口（依赖抽象，不依赖适配器）
  │     ├── InMemory adapter（开发/测试）
  │     └── Sqlite adapter（本地生产闭环）
  ├── presale.contracts
  ├── presale.knowledge / context / answer / disposition / trace
  │
  └── 平台：B0 模型 / B3 ContextService / B1（读取冻结定义）
```

禁止反向：平台不得 import presale；presale 不得直接 new 具体适配器。
