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

## 用 Makefile 复现（推荐）
```bash
make up                 # 起服务
make index-milvus       # catalog.json → Milvus（Hybrid 索引；启动后用 PRESALE_MILVUS_URI 走 Hybrid 检索）
make index-qdrant       # catalog.json → Qdrant
make qa-api             # 启动同步 QA 服务（env 配 LLM/检索）
make models             # 装 bge-large-zh-v1.5（真实语义 embedding，阶段 1 可选）
make teach              # 全量门禁
```

## 版本锁定
镜像 tag 固定：`qdrant/qdrant:v1.12.4`、`milvusdb/milvus:v2.4.1`、`quay.io/coreos/etcd:v3.5.14`。换版本在 `docker-compose.yml` 改后，重新 `docker compose up -d`（会按 lock 复现）。

## 模型（可选、本地）
真实语义 embedding 用 bge-large-zh-v1.5，重排可选 bge-reranker-base：`make models`（`uv sync --extra embedding` + `python scripts/download_models.py all` 经 hf-mirror GET 拉到 `./models`，已 `.gitignore`）。装好后 embedding 用 `PRESALE_EMBEDDING_MODEL=models/bge-large-zh-v1.5`、重排用 `PRESALE_RERANKER_MODEL=models/bge-reranker-base`（离线加载加 `HF_HUB_OFFLINE=1`）。若不想下载模型，用 `PRESALE_EMBEDDING=deterministic` 哈希伪向量先验证管道。

> HuggingFace 直连不通时，`huggingface_hub` 的 HEAD 元数据校验对 hf-mirror 会失败，故用 `scripts/download_bge_zh.py` 以 GET 逐文件下载。

## 检索评估（可量化）
`presale-eval-retrieval`（`make eval` / `make eval-semantic` / `make eval-semantic-rerank`）在 `src/presale/data/dev_catalog.json` 的 8 个商品、22 条改写句 golden set 上，度量段落级排序的 hit@k / MRR / precision@k（检索为商品作用域，故测的是「相关事实段落是否排进 top-k」）。

当前基线（2026-09-19，Milvus 本地文件存储，Hybrid dense+BM25+RRF，top_k=5，n=22；含可选 cross-encoder 重排 bge-reranker-base）：

| 管线 | hit@1 | hit@3 | hit@5 | MRR | prec@5 |
|---|---|---|---|---|---|
| **真实 bge** | 0.64 | 0.91 | 0.95 | 0.78 | 0.23 |
| **真实 bge + reranker** | 0.77 | 0.91 | 0.95 | 0.84 | 0.35 |
| deterministic（伪向量，仅管道验证） | 0.55 | 0.73 | 0.73 | 0.63 | 0.33 |

真实语义嵌入显著领先伪向量；`bge-reranker-base` 重排进一步提升 top-1 准确率（0.64→0.77）与 MRR（0.78→0.84）。后续改动以此表为对比基准。CI 的 `milvus-integration` job 用 deterministic 嵌入跑同一 harness 冒烟（指标须落在 [0,1]），不下载模型。

## 注意
- Milvus **单独** `docker run` 裸镜像无法工作——它需要 etcd 提供元数据，且此仓库用 **本地文件存储**（`COMMON_STORAGETYPE=local`）而非 MinIO。请用 `docker compose up` 一起拉起。
- 为什么没有 MinIO：本机 1Panel 镜像站未缓存 `minio/minio` 镜像（`docker pull` 报 403），故 Milvus 单机用 local 存储以绕开对象存储依赖。**生产/正式若需 MinIO 对象存储**，加回 minio 服务并把 `COMMON_STORAGETYPE` 改回 `remote`、补 `MINIO_ADDRESS`。
- 数据容器可重建，但 volumes 持久化；需要重置删除 volume 时 `docker compose down -v`。
- CI 的真机集成 job（`milvus-integration`）会复用本仓库的 `docker compose up -d etcd milvus` 栈，跑 `tests/b1/test_milvus_integration.py` 的真实 Hybrid e2e（索引 + 检索 + 租户隔离）；需设 `MILVUS_INTEGRATION=1` 才会执行，gate job 自动 skip。本地验证可用：`docker compose up -d etcd milvus && MILVUS_INTEGRATION=1 PRESALE_MILVUS_URI=http://127.0.0.1:19530 uv run pytest -q tests/b1/test_milvus_integration.py`。