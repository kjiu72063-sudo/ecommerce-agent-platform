.PHONY: up down ps models index-qdrant index-milvus qa-api teach

# 本地可复现的外部环境栈（Qdrant + Milvus + etcd + minio）
up:
	docker compose up -d

down:
	docker compose down

ps:
	docker compose ps

# 本地 bge-large-zh-v1.5 模型（真实语义 embedding，阶段 1 可选）
models:
	pip install sentence-transformers

# 把现有 catalog 索引进 Qdrant（确定性 embedding 可先验证管道）
index-qdrant:
	PRESALE_QDRANT_URL=http://localhost:6333 PRESALE_EMBEDDING=deterministic uv run presale-index ./catalog.json

# 把现有 catalog 索引进 Milvus（Hybrid RAG 阶段 1；确定性 embedding 先验证）
index-milvus:
	uv sync --extra hybrid
	PRESALE_MILVUS_URI=http://localhost:19530 PRESALE_EMBEDDING=deterministic uv run presale-index-hybrid ./catalog.json

# 启动同步 QA 服务（用 env 配置真实 LLM/检索）
qa-api:
	uv run presale-qa-api

# 快速自检（全量门禁）
teach:
	uv run pre-commit run --all-files
	uv run pytest -q