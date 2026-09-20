.PHONY: up down ps models index-qdrant index-milvus eval eval-semantic eval-semantic-rerank eval-sweep eval-regression eval-generation eval-generation-regression eval-generation-adversarial eval-generation-e2e qa-api teach

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

# 检索评估：真实语义嵌入 + cross-encoder 重排（推荐 bge-reranker-large，对比无重排看 MRR/ hit@1 提升）
eval-semantic-rerank:
	HF_HUB_OFFLINE=1 PRESALE_EMBEDDING_MODEL=models/bge-large-zh-v1.5 \
	PRESALE_RERANKER_MODEL=models/bge-reranker-large \
	PRESALE_MILVUS_URI=http://localhost:19530 PRESALE_MILVUS_COLLECTION=presale_hybrid_1024 \
	PRESALE_CATALOG=src/presale/data/dev_catalog.json \
	uv run presale-eval-retrieval

# 检索评估：扫描 pool × rrf_k × bm25_weight × 重排方式，找最佳配置（需 make models 含 reranker）
eval-sweep:
	HF_HUB_OFFLINE=1 PRESALE_MILVUS_URI=http://localhost:19530 \
	PRESALE_EMBEDDING_MODEL=models/bge-large-zh-v1.5 \
	python scripts/sweep_retrieval.py --pools 15,30,60 --rrf-ks 60 --bm25-weights 1.0

# 检索回归：per-query 结果与基线 snapshot 对比，任何召回/排序回退即失败（需模型 + Milvus）
eval-regression:
	HF_HUB_OFFLINE=1 PRESALE_EMBEDDING_MODEL=models/bge-large-zh-v1.5 \
	PRESALE_RERANKER_MODEL=models/bge-reranker-large \
	PRESALE_MILVUS_URI=http://localhost:19530 PRESALE_MILVUS_COLLECTION=presale_hybrid_1024 \
	PRESALE_CATALOG=src/presale/data/dev_catalog.json PRESALE_HYBRID_POOL=15 \
	python scripts/eval_regression.py

# 生成端忠实度评估（LLM-as-judge；需 PRESALE_LLM_* 真实密钥 + 模型 + Milvus）
eval-generation:
	HF_HUB_OFFLINE=1 PRESALE_EMBEDDING_MODEL=models/bge-large-zh-v1.5 \
	PRESALE_RERANKER_MODEL=models/bge-reranker-large \
	PRESALE_MILVUS_URI=http://localhost:19530 PRESALE_MILVUS_COLLECTION=presale_hybrid_1024 \
	PRESALE_CATALOG=src/presale/data/dev_catalog.json PRESALE_HYBRID_POOL=15 \
	uv run presale-eval-generation --diagnostics

# 生成端忠实度回归：与基线 snapshot 对比，faithfulness 低于下限或回退即失败
eval-generation-regression:
	HF_HUB_OFFLINE=1 PRESALE_EMBEDDING_MODEL=models/bge-large-zh-v1.5 \
	PRESALE_RERANKER_MODEL=models/bge-reranker-large \
	PRESALE_MILVUS_URI=http://localhost:19530 PRESALE_MILVUS_COLLECTION=presale_hybrid_1024 \
	PRESALE_CATALOG=src/presale/data/dev_catalog.json PRESALE_HYBRID_POOL=15 \
	uv run presale-eval-generation --snapshot tests/fixtures/generation_snapshot.json

# 生成端对抗守卫：证据不足的对抗级 QA（含彻底无证据模拟）不得出现"未判出的编造"（有真实幻觉则失败）
eval-generation-adversarial:
	HF_HUB_OFFLINE=1 PRESALE_EMBEDDING_MODEL=models/bge-large-zh-v1.5 \
	PRESALE_RERANKER_MODEL=models/bge-reranker-large \
	PRESALE_MILVUS_URI=http://localhost:19530 PRESALE_MILVUS_COLLECTION=presale_hybrid_1024 \
	PRESALE_CATALOG=src/presale/data/dev_catalog.json PRESALE_HYBRID_POOL=15 \
	uv run presale-eval-generation --adversarial && \
	uv run presale-eval-generation --adversarial --sever-evidence

# 生成端忠实度评估（真实端到端：走 PresaleQaRunner.ask 完整生产路径，而非评测重建管线）
eval-generation-e2e:
	HF_HUB_OFFLINE=1 PRESALE_EMBEDDING_MODEL=models/bge-large-zh-v1.5 \
	PRESALE_RERANKER_MODEL=models/bge-reranker-large \
	PRESALE_MILVUS_URI=http://localhost:19530 PRESALE_MILVUS_COLLECTION=presale_hybrid_1024 \
	PRESALE_CATALOG=src/presale/data/dev_catalog.json PRESALE_HYBRID_POOL=15 \
	uv run presale-eval-generation --e2e --diagnostics && \
	uv run presale-eval-generation --e2e --adversarial && \
	uv run presale-eval-generation --e2e --adversarial --sever-evidence

# 启动同步 QA 服务（用 env 配置真实 LLM/检索）
qa-api:
	uv run presale-qa-api

# 快速自检（全量门禁）
teach:
	uv run pre-commit run --all-files
	uv run pytest -q