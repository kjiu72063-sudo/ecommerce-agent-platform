# 外部环境部署（可复现）

本目录/根级 `docker-compose.yml` 让 RAG 相关的一票外部服务能从仓库一键复现，避免 ad-hoc `docker run` 的人工漂移。

## 一键拉起
```bash
docker compose up -d        # 起 Qdrant(6333) + Milvus(19530) + etcd + minio
docker compose ps
```
停止：`docker compose down`（保留 volumes）。

| 服务 | 端口 | 用途 |
|---|---|---|
| Qdrant | 6333/6334 | 向量检索（单点/简单） |
| Milvus | 19530/9091 | 向量检索（Hybrid RAG 阶段 1 稠密端） |
| etcd / minio | 2379/9000,9001 | Milvus 依赖（不作为业务入口） |
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
镜像 tag 固定：`qdrant/qdrant:v1.12.4`、`milvusdb/milvus:v2.4.1`、`minio/minio:...`、`etcd:v3.5.14`。换版本在 `docker-compose.yml` 改后，重新 `docker compose up -d`（会按 lock 复现）。

## 模型（可选、本地）
真实语义 embedding 需要 bge-large-zh-v1.5（`make models` → `pip install sentence-transformers`，自动下载模型）。若不想下载，用 `PRESALE_EMBEDDING=deterministic` 哈希伪向量先验证管道。

## 注意
- Milvus **单独** `docker run` 裸镜像无法工作——它依赖 etcd+minio（`ETCD_ENDPOINTS`/`MINIO_ADDRESS`）。请用 `docker compose up` 一起拉起。
- 数据容器可重建，但 volumes 持久化；需要重置删除 volume 时 `docker compose down -v`。
- CI 未自动拉起这些服务（本地/自托管 RAG 栈）；索引与检索在运行时由你环境提供。后续可加 GitHub Actions service-container job 做真机集成测试。