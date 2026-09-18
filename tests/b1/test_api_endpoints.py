"""B1 FastAPI HTTP 端到端测试（TestClient）。"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fastapi.testclient import TestClient

import path_config  # noqa: F401
from registry.api.main import app, reset_service


def load(name):
    return json.loads(
        (path_config.B0_EXAMPLES / "valid" / f"{name}.json").read_text(encoding="utf-8")
    )


class TestApiEndpoints(unittest.TestCase):
    def setUp(self):
        reset_service()
        self.client = TestClient(app)
        self.agent = load("agent-spec")
        self.agent["status"]["phase"] = "draft"  # 允许删除/迁移

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "healthy")

    def test_register_get_list(self):
        register = self.client.post(
            "/api/v1/registry/definitions",
            json={
                "kind": "agent-spec",
                "payload": self.agent,
                "actor_type": "user",
                "actor_id": "usr_test",
            },
        )
        self.assertEqual(register.status_code, 200)
        body = register.json()["data"]
        agent_id = body["id"]
        self.assertIn("content_digest", body)

        get = self.client.get(f"/api/v1/registry/definitions/{agent_id}")
        self.assertEqual(get.status_code, 200)
        self.assertEqual(get.json()["data"]["metadata"]["id"], agent_id)

        listing = self.client.get("/api/v1/registry/definitions")
        self.assertEqual(listing.status_code, 200)
        data = listing.json()["data"]
        self.assertEqual(data["total"], 1)  # total 必须是总数，而非当前页长度
        self.assertEqual(len(data["items"]), 1)

    def test_list_total_ignores_offset(self):
        for _ in range(3):
            resp = self.client.post(
                "/api/v1/registry/definitions",
                json={
                    "kind": "agent-spec",
                    "payload": self.agent,
                    "actor_type": "user",
                    "actor_id": "usr_test",
                },
            )
            self.assertEqual(resp.status_code, 200)
            # 每次修改 key 和 id，避免重复对象冲突
            self.agent["metadata"]["key"] = f"agent-spec-{len(self.agent['metadata']['key'])}-{_}"
            self.agent["metadata"]["id"] = f"agt_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f41{_ + 2}"
        listing = self.client.get("/api/v1/registry/definitions?limit=2&offset=0")
        data = listing.json()["data"]
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["total"], 3)

    def test_transition_to_active(self):
        register = self.client.post(
            "/api/v1/registry/definitions",
            json={
                "kind": "agent-spec",
                "payload": self.agent,
                "actor_type": "user",
                "actor_id": "usr_test",
            },
        ).json()["data"]
        agent_id = register["id"]
        for target in ("testing", "awaiting_approval", "approved", "active"):
            resp = self.client.post(
                f"/api/v1/registry/definitions/{agent_id}/transition",
                json={"target_phase": target, "reason": "test"},
            )
            self.assertEqual(resp.status_code, 200, target)

    def test_versions_and_dependencies_endpoints(self):
        register = self.client.post(
            "/api/v1/registry/definitions",
            json={
                "kind": "agent-spec",
                "payload": self.agent,
                "actor_type": "user",
                "actor_id": "usr_test",
            },
        ).json()["data"]
        agent_id = register["id"]
        versions = self.client.get(f"/api/v1/registry/definitions/{agent_id}/versions")
        self.assertEqual(versions.status_code, 200)
        self.assertGreaterEqual(len(versions.json()["data"]["versions"]), 1)
        deps = self.client.get(f"/api/v1/registry/definitions/{agent_id}/dependencies")
        self.assertEqual(deps.status_code, 200)

    def test_audit_logs(self):
        register = self.client.post(
            "/api/v1/registry/definitions",
            json={
                "kind": "agent-spec",
                "payload": self.agent,
                "actor_type": "user",
                "actor_id": "usr_test",
            },
        ).json()["data"]
        agent_id = register["id"]
        audit = self.client.get("/api/v1/registry/audit")
        self.assertEqual(audit.status_code, 200)
        self.assertGreaterEqual(len(audit.json()["data"]["logs"]), 1)
        filtered = self.client.get(f"/api/v1/registry/audit?resource_id={agent_id}")
        self.assertEqual(filtered.status_code, 200)

    def test_delete_draft(self):
        register = self.client.post(
            "/api/v1/registry/definitions",
            json={
                "kind": "agent-spec",
                "payload": self.agent,
                "actor_type": "user",
                "actor_id": "usr_test",
            },
        ).json()["data"]
        agent_id = register["id"]
        delete = self.client.request(
            "DELETE",
            f"/api/v1/registry/definitions/{agent_id}",
            json={"actor_type": "user", "actor_id": "usr_test"},
        )
        self.assertEqual(delete.status_code, 200)
        self.assertTrue(delete.json()["data"]["deleted"])

    def test_get_missing_returns_404(self):
        resp = self.client.get(
            "/api/v1/registry/definitions/agt_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f999"
        )
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
