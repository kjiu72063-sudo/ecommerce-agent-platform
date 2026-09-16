"""Production composition root for the presale application."""

from __future__ import annotations

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
        options = {
            "sources": self._sources,
            "definition_source": self._definition_source,
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
    ) -> tuple["PresaleRuntimeFactory", SQLitePresaleStore]:
        """Create the single local-production assembly with SQLite adapters."""
        store = SQLitePresaleStore(database)
        factory = cls(
            definition_repository=definition_repository,
            definition_selectors=definition_selectors,
            sources=sources,
            question_repo=SQLiteProductQuestionRepository(store),
            evidence_repo=SQLiteEvidenceRepository(store),
            answer_repo=SQLiteAnswerDraftRepository(store),
            disposition_repo=SQLiteDispositionRepository(store),
            trace_repo=SQLiteRunTraceRepository(store),
            idempotency_repo=SQLiteIdempotencyRepository(store),
        )
        return factory, store
