# V1 售前商品问答 — Ticket 索引

> 依据规格：`docs/spec-v1-presale-product-qa.md`
> 更新时间：2026-09-07
> 状态：已确认依赖与拆分

本目录存放 V1 售前商品问答的 tracer-bullet tickets。每个 ticket 一个文件，按依赖顺序编号。

## 依赖结构

```text
01 契约（无）
 ├─ 02 知识 JSON + 检索 → EvidenceItem
 ├─ 03 ProductQuestion → ContextPackage
 ├─ 04 ContextPackage → AnswerDraft      （依赖 02、03）
 ├─ 05 处置：accepted/edited/...          （依赖 04）
 ├─ 06 运行追溯                          （依赖 04）
 ├─ 07 tracer bullet 全链路测试          （依赖 04、05、06）
 ├─ 08 只读负向 + 失败出口               （依赖 02、03、04）
 ├─ 09 幂等提交                          （依赖 03）
 ├─ 10 保留策略（30 天）                 （依赖 06）
 └─ 11 最小运行入口                      （依赖 07）
```

## 工作顺序

1. **01 → 02 → 03 → 04** 构成最小可验证主路径；
2. **05、06** 补齐业务处置闭环和可追溯性；
3. **07** 是端到端门禁，验证完整 tracer bullet；
4. **08** 强化只读和失败边界；
5. **09、10** 处理幂等与保留；
6. **11** 提供可观察运行入口。

## Ticket 清单

| # | Ticket | 文件 | Blocked by |
|---|---|---|---|
| 01 | 定义 V1 业务对象与最小输入/输出契约 | [01-contracts.md](01-contracts.md) | 无 |
| 02 | 固定商品知识 JSON 与确定性检索 → EvidenceItem | [02-knowledge-retrieval.md](02-knowledge-retrieval.md) | 01 |
| 03 | ProductQuestion → ContextPackage | [03-context-builder.md](03-context-builder.md) | 01 |
| 04 | ContextPackage → AnswerDraft | [04-answer-generator.md](04-answer-generator.md) | 02、03 |
| 05 | AnswerDraft 处置与留痕 | [05-disposition.md](05-disposition.md) | 04 |
| 06 | 运行追溯（Task/Run/Event/provenance） | [06-run-trace.md](06-run-trace.md) | 04 |
| 07 | 端到端 tracer bullet 主路径测试 | [07-e2e-tracer-bullet.md](07-e2e-tracer-bullet.md) | 04、05、06 |
| 08 | 只读负向测试与失败出口覆盖 | [08-readonly-and-failures.md](08-readonly-and-failures.md) | 02、03、04 |
| 09 | 幂等提交 | [09-idempotency.md](09-idempotency.md) | 03 |
| 10 | 保留策略（30 天） | [10-retention.md](10-retention.md) | 06 |
| 11 | 最小可观测运行入口 | [11-run-entrypoint.md](11-run-entrypoint.md) | 07 |

## 状态

Ticket 01–11 已全部完成。V1 售前商品问答 tracer bullet 已可运行并可通过 `presale.cli` 从根目录执行。已提交独立 commit 保持每 ticket 可回滚；全量测试 117 passed，ruff/pre-commit 通过。
