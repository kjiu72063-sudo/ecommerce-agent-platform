.PHONY: up down ps models index-qdrant index-milvus eval eval-semantic eval-semantic-rerank qa-api teach

# 本地可复现的外部环境栈（Qdrant + Milvus + etcd，本地文件存储）
up:
	docker compose up -d

down:
	docker compose down

ps:
	docker compose ps

# 本地模型（bge-large-zh 语义 embedding + bge-reranker 重排；经 hf-mirror GET 拉到 ./models，可复现）
models:
	uv sync --extra embedding
	python scripts/download_models.py all

# 把现有 catalog 索引进 Qdrant（确定性 embedding 可先验证管道）
index-qdrant:
	PRESALE_QDRANT_URL=http://localhost:6333 PRESALE_EMBEDDING=deterministic uv run presale-index ./catalog.json

# 把现有 catalog 索引进 Milvus（Hybrid RAG 阶段 1；确定性 embedding 先验证）
index-milvus:
	uv sync --extra hybrid
	PRESALE_MILVUS_URI=http://localhost:19530 PRESALE_EMBEDDING=deterministic uv run presale-index-hybrid ./catalog.json

# 检索评估：确定性嵌入（快，CI/管道验证用）
eval:
	PRESALE_MILVUS_URI=http://localhost:19530 PRESALE_EMBEDDING=deterministic \
	PRESALE_MILVUS_COLLECTION=presale_hybrid_eval PRESALE_CATALOG=src/presale/data/dev_catalog.json \
	uv run presale-eval-retrieval

# 检索评估：真实语义嵌入（需先 make models 下载 bge，数才有意义）
eval-semantic:
	HF_HUB_OFFLINE=1 PRESALE_EMBEDDING_MODEL=models/bge-large-zh-v1.5 \
	PRESALE_MILVUS_URI=http://localhost:19530 PRESALE_MILVUS_COLLECTION=presale_hybrid_1024 \
	PRESALE_CATALOG=src/presale/data/dev_catalog.json \
	uv run presale-eval-retrieval

# 检索评估：真实语义嵌入 + cross-encoder 重排（对比 eval-semantic 看 MRR 提升）
eval-semantic-rerank:
	HF_HUB_OFFLINE=1 PRESALE_EMBEDDING_MODEL=models/bge-large-zh-v1.5 \
	PRESALE_RERANKER_MODEL=models/bge-reranker-base \
	PRESALE_MILVUS_URI=http://localhost:19530 PRESALE_MILVUS_COLLECTION=presale_hybrid_1024 \
	PRESALE_CATALOG=src/presale/data/dev_catalog.json \
	uv run presale-eval-retrieval

# 启动同步 QA 服务（用 env 配置真实 LLM/检索）
qa-api:
	uv run presale-qa-api

# 快速自检（全量门禁）
teach:
	uv run pre-commit run --all-files
	uv run pytest -q