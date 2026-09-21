"""Production composition root for the presale application."""

from __future__ import annotations

import os

from .adapters.external_retrieval import ExternalRetrieval
from .adapters.openai_generator import OpenAICompatibleGenerator
from .adapters.sqlite import (
    SQLiteAnswerDraftRepository,
    SQLiteDispositionRepository,
    SQLiteEvidenceRepository,
    SQLiteIdempotencyRepository,
    SQLitePresaleStore,
    SQLiteProductQuestionRepository,
    SQLiteRunTraceRepository,
)
from .agent import PresaleAgent
from .definitions import B1DefinitionSource
from .runner import PresaleQaRunner


def openai_generator_from_env() -> OpenAICompatibleGenerator | None:
    """Build the OpenAI-compatible generator from environment configuration.

    Reads PRESALE_LLM_BASE_URL / PRESALE_LLM_MODEL / PRESALE_LLM_API_KEY; returns
    None when any is missing so the default (deterministic) assembly is preserved.
    The API key is never stored in code or docs.
    """
    base_url = os.environ.get("PRESALE_LLM_BASE_URL")
    model = os.environ.get("PRESALE_LLM_MODEL")
    api_key = os.environ.get("PRESALE_LLM_API_KEY")
    if not (base_url and model and api_key):
        return None
    return OpenAICompatibleGenerator(model=model, base_url=base_url, api_key=api_key)


def external_retriever_from_env() -> ExternalRetrieval | None:
    """Build an external retrieval adapter from environment configuration.

    Preference: Hybrid (PRESALE_MILVUS_URI) -> Qdrant (PRESALE_QDRANT_URL) ->
    generic search (PRESALE_RETRIEVAL_BASE_URL). None keeps the deterministic
    retriever as the default.
    """
    from .adapters.hybrid_retrieval import hybrid_retriever_from_env
    from .adapters.qdrant_retrieval import qdrant_retriever_from_env

    if os.environ.get("PRESALE_MILVUS_URI"):
        return hybrid_retriever_from_env()
    if os.environ.get("PRESALE_QDRANT_URL"):
        return qdrant_retriever_from_env()
    if not os.environ.get("PRESALE_RETRIEVAL_BASE_URL"):
        return None
    return ExternalRetrieval()


class PresaleRuntimeFactory:
    """Build runners wired to B1 definitions and optional persistence ports."""

    def __init__(
        self,
        *,
        definition_repository,
        definition_selectors: dict[str, dict[str, str]],
        sources,
        **persistence_ports,
    ):
        self._definition_source = B1DefinitionSource(
            definition_repository, selectors=definition_selectors
        )
        self._sources = sources
        self._persistence_ports = persistence_ports

    def create_runner(self, **overrides) -> PresaleQaRunner:
        min_evidence = int(os.environ.get("PRESALE_MIN_EVIDENCE_FOR_ANSWER", "1"))
        options = {
            "sources": self._sources,
            "definition_source": self._definition_source,
            "min_evidence_for_answer": min_evidence,
            **self._persistence_ports,
            **overrides,
        }
        return PresaleQaRunner(**options)

    def create_agent(self, **overrides) -> PresaleAgent:
        """Create a Harness-drivable Agent over the same wiring as a runner."""
        return PresaleAgent(self.create_runner(**overrides))

    def create_openai_agent(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        transport=None,
        **overrides,
    ) -> PresaleAgent:
        """Create a Harness-drivable Agent whose generation ring calls an
        OpenAI-compatible chat completion.

        Explicit assembly: external LLM calls only happen through this entry
        (or by injecting a generator); the default remains deterministic.
        """
        generator = OpenAICompatibleGenerator(
            model=model, base_url=base_url, api_key=api_key, transport=transport
        )
        return self.create_agent(generator=generator, **overrides)

    @classmethod
    def create_sqlite(
        cls,
        *,
        database,
        definition_repository,
        definition_selectors: dict[str, dict[str, str]],
        sources,
        generator=None,
        retriever=None,
    ) -> tuple["PresaleRuntimeFactory", SQLitePresaleStore]:
        """Create the single local-production assembly with SQLite adapters.

        ``generator``/``retriever`` may be injected explicitly, or read from
        environment (PRESALE_LLM_* / PRESALE_RETRIEVAL_BASE_URL) when None;
        otherwise the deterministic defaults are used.
        """
        store = SQLitePresaleStore(database)
        ports = {
            "question_repo": SQLiteProductQuestionRepository(store),
            "evidence_repo": SQLiteEvidenceRepository(store),
            "answer_repo": SQLiteAnswerDraftRepository(store),
            "disposition_repo": SQLiteDispositionRepository(store),
            "trace_repo": SQLiteRunTraceRepository(store),
            "idempotency_repo": SQLiteIdempotencyRepository(store),
        }
        generator = generator if generator is not None else openai_generator_from_env()
        if generator is not None:
            ports["generator"] = generator
        retriever = retriever if retriever is not None else external_retriever_from_env()
        if retriever is not None:
            ports["retriever"] = retriever
        factory = cls(
            definition_repository=definition_repository,
            definition_selectors=definition_selectors,
            sources=sources,
            **ports,
        )
        return factory, store

    @classmethod
    def create_postgres(
        cls,
        *,
        dsn: str | None = None,
        definition_repository,
        definition_selectors: dict[str, dict[str, str]],
        sources,
        generator=None,
        retriever=None,
    ) -> tuple["PresaleRuntimeFactory", "PostgresPresaleStore"] | tuple[None, None]:
        """Create a production assembly backed by PostgreSQL.

        ``dsn`` defaults to ``PRESALE_PG_DSN`` env var. Returns
        ``(None, None)`` when no DSN is available.
        """
        from .adapters.postgres import (
            PostgresAnswerDraftRepository,
            PostgresDispositionRepository,
            PostgresEvidenceRepository,
            PostgresIdempotencyRepository,
            PostgresPresaleStore,
            PostgresProductQuestionRepository,
            PostgresRunTraceRepository,
        )

        dsn = dsn or os.environ.get("PRESALE_PG_DSN")
        if not dsn:
            return None, None

        store = PostgresPresaleStore(dsn=dsn)
        ports = {
            "question_repo": PostgresProductQuestionRepository(store),
            "evidence_repo": PostgresEvidenceRepository(store),
            "answer_repo": PostgresAnswerDraftRepository(store),
            "disposition_repo": PostgresDispositionRepository(store),
            "trace_repo": PostgresRunTraceRepository(store),
            "idempotency_repo": PostgresIdempotencyRepository(store),
        }
        generator = generator if generator is not None else openai_generator_from_env()
        if generator is not None:
            ports["generator"] = generator
        retriever = retriever if retriever is not None else external_retriever_from_env()
        if retriever is not None:
            ports["retriever"] = retriever
        factory = cls(
            definition_repository=definition_repository,
            definition_selectors=definition_selectors,
            sources=sources,
            **ports,
        )
        return factory, store
