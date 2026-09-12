"""Production composition root for the presale application."""

from __future__ import annotations

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
