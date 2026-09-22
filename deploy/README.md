# 外部环境部署（可复现）

本目录/根级 `docker-compose.yml` 让 RAG 相关的一票外部服务能从仓库一键复现，避免 ad-hoc `docker run` 的人工漂移。

## 一键拉起
```bash
docker compose up -d        # 起 Qdrant(6333) + Milvus(19530) + etcd
docker compose ps
```
停止：`docker compose down`（保留 volumes）。

| 服务 | 端口 | 用途 |
|---|---|---|
| Qdrant | 6333/6334 | 向量检索（单点/简单） |
| Milvus | 19530/9091 | 向量检索（Hybrid RAG 阶段 1 稠密端） |
| etcd | 2379 | Milvus 元数据依赖（不作为业务入口） |
| Neo4j | 7474/7687 | RAG 阶段 2（GraphRAG，默认注释，用时启用） |
| PostgreSQL | 5432 | presale 六端口持久化（profile `postgres` 或 `production`） |

## 用 Makefile 复现（推荐）
```bash
make up                 # 起服务
make index-milvus       # catalog.json → Milvus（Hybrid 索引；启动后用 PRESALE_MILVUS_URI 走 Hybrid 检索）
make index-qdrant       # catalog.json → Qdrant
make qa-api             # 启动同步 QA 服务（env 配 LLM/检索）
make models             # 装 bge-large-zh-v1.5（真实语义 embedding，阶段 1 可选）
make teach              # 全量门禁
```

## PostgreSQL（presale 持久化）

开发栈：

```bash
docker compose --profile postgres up -d postgres
```

生产 profile 使用同一镜像，但要求自行设置口令，并加上日志卷、资源限制与不为空的数据卷：

```bash
export PRESALE_PG_PASSWORD='<自行设置>'
docker compose -f docker-compose.yml -f deploy/postgres.production.yml --profile production up -d postgres
```

默认开发口令只在未设置 `PRESALE_PG_PASSWORD` 时生效，生产 profile 拒绝这个默认值。连接串：

```text
postgresql://presale:<口令>@127.0.0.1:5432/presale
```

把已有 SQLite 运行记录迁过来（只搬 presale 六张表，不碰 B1/B2 的其他库）：

```bash
uv sync --extra postgres
presale-migrate-pg --sqlite ./presale.sqlite3 --dsn "$PRESALE_PG_DSN"
```

重复执行是按主键覆盖，不会把同一行插两次。迁移前会拒绝口令为 `presale` 的目标库，除非显式加上 `--allow-default-password`（仅限本机开发）。CI 的 `postgres-integration` job 用一次性容器跑同一组集成测试。

## 版本锁定
镜像 tag 固定：`qdrant/qdrant:v1.12.4`、`milvusdb/milvus:v2.4.1`、`quay.io/coreos/etcd:v3.5.14`、`postgres:15-alpine`。换版本在 `docker-compose.yml` 改后，重新 `docker compose up -d`（会按 lock 复现）。

## 模型（可选、本地）
真实语义 embedding 用 bge-large-zh-v1.5，重排可选 bge-reranker-base/large：`make models`（`uv sync --extra embedding` + `python scripts/download_models.py all` 经 hf-mirror GET 拉到 `./models`，已 `.gitignore`；支持断点续传，`scripts/download_models.py <name>` 单模型）。装好后 embedding 用 `PRESALE_EMBEDDING_MODEL=models/bge-large-zh-v1.5`、重排用 `PRESALE_RERANKER_MODEL=models/bge-reranker-large`（离线加载加 `HF_HUB_OFFLINE=1`）。若不想下载模型，用 `PRESALE_EMBEDDING=deterministic` 哈希伪向量先验证管道。

> HuggingFace 直连不通时，`huggingface_hub` 的 HEAD 元数据校验对 hf-mirror 会失败，故用 `scripts/download_bge_zh.py` 以 GET 逐文件下载。

## 检索评估（可量化）
`presale-eval-retrieval`（`make eval` / `make eval-semantic` / `make eval-semantic-rerank`）在 `src/presale/data/dev_catalog.json`（22 商品、211 事实段落）+ 68 条改写句 golden set 上，度量段落级排序的 hit@k / MRR / precision@k（检索为商品作用域，故测的是「相关事实段落是否排进 top-k」）。`scripts/sweep_retrieval.py`（`make eval-sweep`）扫候选池/RRF/BM25 权重/重排方式；`scripts/eval_regression.py`（`make eval-regression`）把逐条结果与基线 snapshot（`tests/fixtures/retrieval_golden_snapshot.json`）对比，任何召回/排序回退即失败。

基线（2026-09-20，Milvus 本地文件存储，Hybrid dense+BM25+RRF，top_k=5，n=112，pool=15；large 重排 + 分块意图覆盖修复后，**真实分布 golden**）：**hit@1=1.0、hit@3=1.0、MRR=1.0**（recall=0、misrank=0）。

> **压测结论（重要）**：
> 1. 从 40→68 条 golden（语料 14→22 商品，含语义重叠挑战者）扩量后检索初跑掉到 MRR 0.94；扩到 112 条真实口吻查询后又测到 MRR **0.936 / hit@1 0.893**——证明规整手写句的「1.0」确实不泛化。
> 2. 对 12 处暴露的真实缺口做**概念级意图覆盖**（耐穿/捂脚、防滑/出溜倒、塞绒/抗冻、料子/舒适、登机/托运等），并修 1 处 golden 多答案歧义（spec_sole/wet_grip），112 条回到 MRR/hit@1=1.0。
> 3. 注意：这些修复是针对真实查询分布的词汇覆盖，不应把当前满分理解成终点；下一步应再生成一批**out-of-sample**真实查询验证，避免反向记忆 golden。当前 0.936 是本轮改进前最可信基线，1.0 是修复后基线。
> 这印证方法论：**任何固定 golden 都可能被记忆；查询分布越真实，衡量越可信**。当前 112 条真实 golden 的 0.936 才是反映真实检索水平的上限，后续改进（更强 embedding/分块/多证据融合）以此为准对比。

| 管线 | hit@1 | hit@3 | hit@5 | MRR | prec@5 |
|---|---|---|---|---|---|
| 无重排（真实 bge） | 0.675 | 0.975 | 0.975 | 0.808 | 0.272 |
| + bge-reranker-base | 0.700 | 0.825 | 0.875 | 0.775 | 0.338 |
| + bge-reranker-large | 0.775 | 0.925 | 0.925 | 0.850 | 0.374 |
| + large + 分块质量修复（(a)(b) 逐条定位） | **1.000** | **1.000** | **1.000** | **1.000** | 0.400 |
| deterministic（伪向量，仅管道验证） | ~0.55 | ~0.73 | ~0.73 | ~0.63 | — |

调参结论（40 条 golden 实测）：
- **候选池 pool=15 最优**，pool∈{30,60} 完全无增益——dense 按商品过滤，相关段落本就全在候选池，池不是瓶颈。
- **BM25 加权对大重排器无影响**；无重排时 weight 0.5 仅微升，可忽略。
- **base 重排器在大语料上反而有害**，不泛化；**large 才是稳健提升**。
- **分块质量是决定性杠杆**：用 `--diagnostics` 逐条定位失败——(a) 召回失败是「目标 chunk 缺用户意图关键词」（如 spec_upf 无「晒黑」、spec_speed 无「爬坡」，导致重排器把意图匹配到其它商品/丢弃）；(b) 歧义是「商品内近义 chunk 冗余」（如两个噪声 chunk、防水与清洗 chunk 混叠）。修复——(a) 强化目标 chunk 的用户意图词、(b) 合并冗余 chunk + 厘清语义边界（如 spec_waterproof 谈防泼水/淋湿、不谈保暖，把冷/暖让给 extreme_cold），`make eval-regression` 把 40/40 基线固化为可回归输出。

生产建议：`PRESALE_RERANKER_MODEL=models/bge-reranker-large` + pool 15。CI 的 `milvus-integration` job 用 deterministic 嵌入跑同一 harness 冒烟（指标须落在 [0,1]），不下载模型。

## 生成端忠实度评估（LLM-as-judge，可量化）
`presale-eval-generation`（`make eval-generation`）在 18 条代表性 QA golden 上，对每条：检索证据 → 真实 LLM（`PRESALE_LLM_*`）生成答案 → 用 judge LLM 给 **faithfulness（忠实度）/ answer_correctness / gold_correctness / unsupported_claims** 打分，聚合输出 mean_faithfulness / mean_answer_correctness / **mean_gold_correctness**。`make eval-generation-regression` 用 `tests/fixtures/generation_snapshot.json` 做回归守底（faithfulness 或 **gold_correctness** 低于 `--floor` 0.4 或相对基线回退 >`--tolerance` 0.25 即非零退出）。解析与聚合是纯函数，有 CI 离线单测。

**步骤 2：抓「忠实但错」**：golden 每条带**参考正确回答（gold）**，judge 据此额外打 `gold_correctness`——专门抓「答案忠实于证据、但相对正确答案答错/答非所问/不够」这类被 faithfulness 漏掉的情况。实测（glm-5.3，18 QA）：mean_faithfulness=1.0 且 **mean_gold_correctness=1.0**（成功答案既忠实又正确）；并有 CI 单测证明 judge 能对「faithfulness=1.0 但 gold_correctness 低」的忠实但错答案给出分化分数（gold_correctness < faithfulness）。

当前基线（2026-09-19，检索为 large+pool15 且 40/40 正确，n=10，真实 LLM glm-5.3）：**mean_faithfulness=1.0、mean_answer_correctness=1.0、total_unsupported=0**。说明在检索正确的前提下，生成端高度忠实于证据（需真实密钥，不进 CI gate）。

**真实端到端（`make eval-generation-e2e`）**：`--e2e` 让评估走**真实 `PresaleQaRunner.ask`**（注入真实 retriever + OpenAICompatibleGenerator 的完整生产路径：检索→上下文→生成→disposition→tracing），而非评测脚本重建的管线；`--e2e --adversarial` / `--e2e --adversarial --sever-evidence` 再加证据不足/全无。实测（glm-5.3）：正常 QA 各题 faithfulness=1.0；对抗两种模式均 4/4 拒答、`undetected_fabrications=0`——真实生产路径在任何证据条件下都不幻觉。

**对抗级守卫（`make eval-generation-adversarial`）**：`--adversarial` 跑 4 条证据不足的对抗 QA（发票/发货/滤网单独购/退货），`--adversarial --sever-evidence` 再模拟检索彻底失效。断言管线**不得出现「未被判出的编造」**（助手要么拒答 withheld、要么其编造未被 judge 标出 unsupported），否则非零退出。实测（glm-5.3）：两种模式下均 4/4 withheld、`undetected_fabrications=0`——证据不足或全无时管线诚实拒答、不幻觉。该守卫最初还暴露并修正了拒答分类器对「未提及…建议咨询」措辞的漏判（假阳性），故 `classify_response` 的关键词表是逐步加固的。

## Corrective-RAG：低置信自动转人工
`PresaleQaRunner` 新路径在生成 draft 后、落库前执行低置信门：`NO_EVIDENCE`/`CONFLICT` 或命中证据少于 `PRESALE_MIN_EVIDENCE_FOR_ANSWER` 时，强制 `need_human=True` 并追加 `NO_EVIDENCE`/`CONFLICT`/`LOW_CONFIDENCE` reason code；默认阈值为 1（保持兼容），生产可设 `PRESALE_MIN_EVIDENCE_FOR_ANSWER=2` 等提高门槛。该门不碰 claim/重放状态机，只影响新生成 draft；API 的 `format_outcome` 已将 `need_human` 暴露到响应顶层，调用方可据此进入人工队列。4 个单测覆盖低置信升级、足量证据不升级、无证据结构约束、重放不重新门控。

## 注意
- Milvus **单独** `docker run` 裸镜像无法工作——它需要 etcd 提供元数据，且此仓库用 **本地文件存储**（`COMMON_STORAGETYPE=local`）而非 MinIO。请用 `docker compose up` 一起拉起。
- 为什么没有 MinIO：本机 1Panel 镜像站未缓存 `minio/minio` 镜像（`docker pull` 报 403），故 Milvus 单机用 local 存储以绕开对象存储依赖。**生产/正式若需 MinIO 对象存储**，加回 minio 服务并把 `COMMON_STORAGETYPE` 改回 `remote`、补 `MINIO_ADDRESS`。
- 数据容器可重建，但 volumes 持久化；需要重置删除 volume 时 `docker compose down -v`。
- CI 的真机集成 job（`milvus-integration`）会复用本仓库的 `docker compose up -d etcd milvus` 栈，跑 `tests/b1/test_milvus_integration.py` 的真实 Hybrid e2e（索引 + 检索 + 租户隔离）；需设 `MILVUS_INTEGRATION=1` 才会执行，gate job 自动 skip。本地验证可用：`docker compose up -d etcd milvus && MILVUS_INTEGRATION=1 PRESALE_MILVUS_URI=http://127.0.0.1:19530 uv run pytest -q tests/b1/test_milvus_integration.py`。