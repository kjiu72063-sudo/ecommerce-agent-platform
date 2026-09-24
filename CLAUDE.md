# CLAUDE.md

操作约定（短小精炼）。权威文档入口见 `AGENTS.md`；此处只记真实 LLM 验收中已踩过的坑与对应规则。

## 真实 LLM 验收（`real-llm-acceptance`）

入口：本地 `make eval-real-acceptance`；CI 仅 `workflow_dispatch` 手动触发（PR 不跑、不烧密钥）。
Secrets：`PRESALE_LLM_BASE_URL` / `PRESALE_LLM_MODEL` / `PRESALE_LLM_API_KEY`。
端点：`llm.goaichat.top`（glm-5.3，推理模型）；索引与评估统一 `PRESALE_EMBEDDING=deterministic`。

## 跨境间歇故障：诊断

**症状**：CI `ubuntu-latest`（海外 runner）间歇出现 `502` / `429` / `ReadTimeout`；本机（国内）通常正常。已知一次连续多轮失败后，本机 curl 也超时，属 provider 短暂不可用，不是代码问题。

**先分流，再改代码**：

1. **凭据 / 配置**：`401`/`403`/`404` 或缺变量 → 查 secrets 与 env，与跨境无关。
2. **缺 `PRESALE_EMBEDDING=deterministic`** → CI 会去装 `sentence_transformers` 直接 `ModuleNotFoundError`（建索引与评估步骤必须同变量）。
3. **`502`/`ReadTimeout`** → 跨境网关或推理模型长响应；先本机 `curl` 同一 `/chat/completions`。本机通 = CI 链路问题；本机也不通 = provider 故障，停手等恢复。
4. **`429`** → 自己限流。近 1 小时是否连跑过多次完整 e2e（每次约 36 次调用）？是则冷却 ≥3 分钟再触发，不要连环重跑。
5. **本机也通、CI 仍 5xx** → 海外 runner → 该端点的间歇故障；重试已内置，可隔几分钟重触发一次 `workflow_dispatch`，仍失败则记为链路问题，不改幂等逻辑。

## 重试与顺序规则（已实现，勿回退）

- **重放先于 e2e**：重放只 1–2 次调用，趁 provider 新鲜先跑；e2e 按题容错，可吸收突发后的抖动。
- **重放首次生成**：最多 3 次尝试，退避 `30s` / `60s`（分钟级，吸收 429/502；秒级不够）。
- **重放第二次调用不重试**：必须读已落库草稿；`generator_calls` 必须与首次成功后持平，否则验收失败。
- **超时**：`PRESALE_GEN_TIMEOUT_S=120`（glm-5.3 推理耗时长，默认 60s 不够）。
- **e2e 单题错误不挡门禁**：errors 不进 snapshot 比较；门禁看 `regressions`（分数回退 / 低于 floor / 快照缺 key）。
- **不连环重触发**：一次失败先按上节分流；确认是限流/provider 就冷却，不要在失败窗口内反复 `gh workflow run`。

## 快照与 golden

- golden 18 题；`tests/fixtures/generation_snapshot.json` 必须覆盖全部会成功的 key，否则报 `new question` 回退（exit 1）。
- 新增 golden 题目且本机实测达标后，用 `--save` 或手工把该 key 以实测分数写入快照，再合入。
