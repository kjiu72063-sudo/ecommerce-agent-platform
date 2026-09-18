import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import path_config
from registry import DefinitionFilter, InMemoryDefinitionRepository, SQLiteDefinitionRepository


def run(coro):
    return asyncio.run(coro)


class DefinitionRepositoryContractMixin:
    def make_repo(self):
        raise NotImplementedError

    def test_create_read_update_list_delete_contract(self):
        repo, cleanup = self.make_repo()
        try:
            obj = json.loads(
                (path_config.B0_EXAMPLES / "valid" / "agent-spec.json").read_text(encoding="utf-8")
            )
            object_id = run(repo.create(obj))
            self.assertEqual(run(repo.get_by_id(object_id))["metadata"]["id"], object_id)
            self.assertEqual(run(repo.count_by_filter(DefinitionFilter())), 1)
            self.assertTrue(run(repo.update(object_id, 1, {"status": {"phase": "draft"}})))
            self.assertFalse(run(repo.update(object_id, 1, {"status": {"phase": "active"}})))
            self.assertEqual(len(run(repo.list_by_filter(DefinitionFilter(), 10, 0))), 1)
            self.assertTrue(run(repo.delete(object_id)))
            self.assertIsNone(run(repo.get_by_id(object_id)))
        finally:
            cleanup()


class TestInMemoryDefinitionRepository(DefinitionRepositoryContractMixin, unittest.TestCase):
    def make_repo(self):
        repo = InMemoryDefinitionRepository()
        return repo, lambda: None


class TestSQLiteDefinitionRepository(DefinitionRepositoryContractMixin, unittest.TestCase):
    def make_repo(self):
        tmp = tempfile.TemporaryDirectory()
        repo = SQLiteDefinitionRepository(Path(tmp.name) / "registry.sqlite3")
        return repo, lambda: (repo.close(), tmp.cleanup())
