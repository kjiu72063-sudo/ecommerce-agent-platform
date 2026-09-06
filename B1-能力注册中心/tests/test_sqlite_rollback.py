import asyncio
import json
import tempfile
import unittest
from pathlib import Path
import sys
import path_config
from registry import RegistryService, SQLiteDefinitionRepository


class FailingAuditRepository(SQLiteDefinitionRepository):
    async def save_audit_log(self, *args, **kwargs):
        raise RuntimeError("audit failure")


class TestSQLiteRollback(unittest.TestCase):
    def test_register_rolls_back_all_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "registry.sqlite3"
            payload = json.loads((path_config.B0_EXAMPLES / "valid" / "agent-spec.json").read_text(encoding="utf-8"))
            repo = FailingAuditRepository(db)
            with self.assertRaises(RuntimeError):
                asyncio.run(RegistryService(repo).register_definition("agent-spec", payload, {"actor_type": "user", "actor_id": "usr_test"}))
            repo.close()
            reopened = SQLiteDefinitionRepository(db)
            self.assertEqual(asyncio.run(reopened.count_by_filter(__import__('registry').DefinitionFilter())), 0)
            reopened.close()


if __name__ == "__main__":
    unittest.main()
