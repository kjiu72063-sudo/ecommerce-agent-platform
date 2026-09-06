import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import path_config
from path_config import B0_EXAMPLES
from registry import DefinitionFilter, RegistryService, SQLiteDefinitionRepository


def run(coro):
    return asyncio.run(coro)


class TestSQLiteDefinitionRepository(unittest.TestCase):
    def test_register_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "registry.sqlite3"
            payload = json.loads((B0_EXAMPLES / "valid" / "agent-spec.json").read_text(encoding="utf-8"))
            repo = SQLiteDefinitionRepository(db)
            service = RegistryService(repo)
            result = run(service.register_definition("agent-spec", payload, {"actor_type": "user", "actor_id": "usr_test"}))
            repo.close()

            reopened = SQLiteDefinitionRepository(db)
            obj = run(reopened.get_by_id(result["id"]))
            self.assertEqual(obj["metadata"]["content_digest"], result["content_digest"])
            self.assertEqual(run(reopened.count_by_filter(DefinitionFilter())), 1)
            self.assertEqual(len(run(reopened.get_versions(result["id"]))), 1)
            self.assertGreaterEqual(len(reopened._audit_logs), 1)
            reopened.close()


if __name__ == "__main__":
    unittest.main()
