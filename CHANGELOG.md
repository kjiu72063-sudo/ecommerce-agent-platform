# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/), versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Direction 5 business agents (mock external services)**: `LiveClipperAgent` (mock ASR transcript + mock ffmpeg cut; deterministic product-segment extraction) and `ContentCreatorAgent` (template copy + mock image generator). Both emit NEED_HUMAN drafts per the no-evidence contract. `presale-eval --mode live-clipper|content-creator` offline goldens. 11 tests. Baseline 390.
- **Direction 8 Markdown report + golden versioning**: `render_markdown` / `--output *.md` emit a metric table and per-question preview; every eval report stamps `golden_meta` (generation/review golden versions + sizes, catalog sha256 prefix, timestamp). `presale-eval-generation --save` writes `_meta` into the generation snapshot. Update policy documented in `deploy/README.md`. 4 tests. Baseline 378.
- **Direction 8 review / multi-agent eval modes**: `presale-eval --mode review` scores ReviewAnalyzerAgent on a deterministic golden (sentiment accuracy, keyword recall, need-human rate); `--mode multi-agent` evaluates Presale→Review via AgentCoordinator (terminal distribution, short-circuit rate, mean sub-agents). Both fully offline — no Milvus/LLM. 4 tests. Baseline 374.
- **Direction 8 e2e latency & cost**: `CallMeter` instruments generation/judge transports; e2e report gains `latency` (wall/mean ask/judge, per-call p50/p95), `tokens` (prompt/completion split by role), and optional `cost.estimated_usd` from `PRESALE_LLM_INPUT_PRICE_PER_M` / `PRESALE_LLM_OUTPUT_PRICE_PER_M`. Per-question rows carry `ask_latency_ms` / `judge_latency_ms` / `total_latency_ms`. `summarize()` appends latency/tokens/cost. Baseline 370.
- **Direction 7 real LLM acceptance**: `--idempotency-replay` runs one real question twice through durable SQLite state and fails if the second call regenerates; manual `workflow_dispatch` CI job runs e2e faithfulness + generation snapshot regression + replay (secrets `PRESALE_LLM_*`, never on PRs). Offline tests cover the replay contract. Baseline 366.
- **AgentCoordinator** (方向4): sequential multi-agent orchestration. The previous answer text is the next question; NEED_HUMAN or MAX_STEPS short-circuits the rest. Presale → Review use case. 9 tests.
- **RepairLoop / ReviewRefineLoop / ReactLoop** (方向3): deterministic step-signal strategies. Exhausted attempts stop rather than finalize. 14 tests.
- **Retrieval regression gate** (方向2): CI compares `presale-eval --mode retrieval` against the committed snapshot and fails on regression.
- **ReviewAnalyzerAgent** (`D-01`): New business agent with `retrieve_knowledge` + `analyze_review` tools. Deterministic sentiment analysis and keyword extraction. Always requires human review per AnswerDraft evidence contract. 8 tests.
- **PostgreSQL adapters** (`B-01/B-02/B-03`): `PostgresPresaleStore` + 6 PostgreSQL repositories (Question/Evidence/Answer/Disposition/Idempotency/Trace). `PresaleRuntimeFactory.create_postgres()` assembly entry. Docker Compose PostgreSQL service. 7 integration tests.
- **LLM integration tests** (`E-01/E-02`): `create_openai_agent()` assembly + failure paths (empty/malformed/exception). `create_sqlite()` full assembly + idempotent replay + failure path. 7 tests.
- **LoopStrategy Protocol** (`B5 T01`): `LoopStrategy` protocol (structural typing), `SinglePassLoop` (backward-compatible default), `StepContext` dataclass, `Loop = SinglePassLoop` alias.
- **Harness multi-step loop** (`B5 T02`): `Harness.execute` passes `StepContext(step_index, previous_tool_calls)` at step N+1. MAX_STEPS terminal outputs last answer_draft.
- **RetryOnLowEvidenceLoop** (`B5 T03`): Deterministic retry strategy based on AgentStep signals. `LoopDecision.STOP` for retry exhaustion.
- **Agent protocol update**: `Agent.run` signature extended with optional `step_context: StepContext | None = None`.
- **Baseline sync CI check**: `scripts/check_baseline.py` verifies ledger matches actual test count.
- **Retro documents**: `docs/retro-rag-eval-tuning.md`, `docs/retro-b5b6-loop-engine.md`.
- **ADR**: `docs/adr/0001-agent-protocol-step-context.md`.
- **Specs**: `docs/spec-b5-loop-engine.md`, `docs/spec-b6-business-agent.md`.

### Fixed
- 39 pyright type errors in `src/registry/` and `src/runtime/` (all `param: T = None` → `param: T | None = None`).
- Port boundary violations: `generation_eval.py` lazy import, `sweep_retrieval.py` parameterized factory, `generate_realistic_golden.py` lazy import.
- Structural issues R-1 through R-5 (README baseline, pyright scope, module boundaries, Loop CONTINUE semantics, `__all__` position).
- Stale B5 development guide marked deprecated.

### Changed
- pyright scope expanded: `src/presale` + `src/agent_runtime` + `src/context` + `src/registry` + `src/runtime`.
- CODING_STANDARDS: added Rule 4 (LoopStrategy & Agent protocol changes).
- Docker Compose: added PostgreSQL 15-alpine service.
- `pyproject.toml`: added `asyncpg` optional dependency, `src/review_agent` module.

### Removed
- 22 stale remote branches cleaned up.
- 18 stale local branches cleaned up.

## [v1.2-presale-qa-service] - 2026-09-16

### Added
- Deployable presale QA service entry (`presale-qa-api`).
- Observability for presale QA service (metrics endpoint).
- B4 Harness/Loop/Agent integration with PresaleAgent.

## [v1.1-presale-external-llm] - 2026-09-15

### Added
- OpenAI-compatible LLM generator adapter.
- External retrieval adapter (Qdrant/Milvus/Hybrid).
- Corrective-RAG: low-confidence retrieval auto-escalates to human.

## [v1.0-presale-converged] - 2026-09-14

### Added
- V1 presale QA converged baseline: 202 passed.
- SQLite persistence, idempotency, 30-day retention.
- RuntimeFactory assembly with SQLite adapters.
