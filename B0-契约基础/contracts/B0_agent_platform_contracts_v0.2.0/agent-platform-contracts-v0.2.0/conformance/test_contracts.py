from __future__ import annotations

import hashlib
import json
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from agent_platform_contracts.models import RESOURCE_MODELS
from agent_platform_contracts.policies import (
    activation_history_is_append_only,
    can_auto_retry,
    canonical_json,
    canonical_sha256,
    combine_permission_decisions,
    definition_is_resolvable,
    lease_allows_commit,
    model_switch_boundary,
    scoped_task_idempotency_key,
    scoped_tool_idempotency_key,
)
from agent_platform_contracts.state_machines import STATE_MACHINES, StateTransitionError, transition


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILES = sorted((ROOT / "schemas").rglob("*.schema.json"))
VALID_FILES = sorted((ROOT / "examples" / "valid").glob("*.json"))
INVALID_FILES = sorted((ROOT / "examples" / "invalid").glob("*.json"))


class ContractConformanceTests(unittest.TestCase):
    def test_exactly_fifteen_core_resource_models(self) -> None:
        self.assertEqual(15, len(RESOURCE_MODELS))

    def test_seventeen_schema_documents_exist(self) -> None:
        self.assertEqual(17, len(SCHEMA_FILES))

    def test_schema_documents_are_draft_2020_12_and_closed(self) -> None:
        for path in SCHEMA_FILES:
            with self.subTest(path=path.name):
                schema = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
                self.assertTrue(schema["$id"].endswith(path.name))
                self.assertEqual("0.2.0", schema["x-contract-version"])
                self.assertIs(schema["additionalProperties"], False)
                for def_name, definition in schema.get("$defs", {}).items():
                    if definition.get("type") == "object" and "properties" in definition:
                        self.assertIs(definition.get("additionalProperties"), False, def_name)

    def test_all_schemas_pass_draft_2020_12_meta_validation(self) -> None:
        for path in SCHEMA_FILES:
            with self.subTest(path=path.name):
                Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))

    def test_all_valid_examples_pass_exported_json_schema(self) -> None:
        for path in VALID_FILES:
            name = path.stem
            group = "definitions" if name in {
                "agent-spec", "skill-manifest", "tool-manifest", "prompt-package",
                "model-policy", "context-policy", "loop-profile", "permission-profile",
            } else "runtime"
            schema_path = ROOT / "schemas" / group / f"{name}.schema.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            instance = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(example=name):
                Draft202012Validator(schema, format_checker=FormatChecker()).validate(instance)

    def test_structurally_invalid_examples_fail_exported_json_schema(self) -> None:
        structural_cases = {
            "agent-spec-extra-field",
            "loop-zero-iterations",
            "permission-default-allow",
            "task-missing-idempotency-key",
            "run-latest-dependency",
            "checkpoint-zero-sequence",
            "event-zero-sequence",
        }
        for case_name in structural_cases:
            case = json.loads((ROOT / "examples" / "invalid" / f"{case_name}.json").read_text(encoding="utf-8"))
            target = case["target_model"]
            group = "definitions" if target in {
                "agent-spec", "skill-manifest", "tool-manifest", "prompt-package",
                "model-policy", "context-policy", "loop-profile", "permission-profile",
            } else "runtime"
            schema = json.loads((ROOT / "schemas" / group / f"{target}.schema.json").read_text(encoding="utf-8"))
            with self.subTest(example=case_name):
                errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(case["payload"]))
                self.assertTrue(errors)

    def test_all_valid_examples_pass_reference_models(self) -> None:
        self.assertEqual(15, len(VALID_FILES))
        for path in VALID_FILES:
            name = path.stem
            with self.subTest(example=name):
                payload = json.loads(path.read_text(encoding="utf-8"))
                RESOURCE_MODELS[name].model_validate(payload)

    def test_all_invalid_examples_are_rejected(self) -> None:
        self.assertEqual(19, len(INVALID_FILES))
        code_pattern = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
        for path in INVALID_FILES:
            with self.subTest(example=path.stem):
                case = json.loads(path.read_text(encoding="utf-8"))
                self.assertRegex(case["expected_error_code"], code_pattern)
                with self.assertRaises(ValidationError):
                    RESOURCE_MODELS[case["target_model"]].model_validate(case["payload"])

    def test_definition_references_are_exact_and_never_latest(self) -> None:
        for path in VALID_FILES:
            rendered = path.read_text(encoding="utf-8")
            with self.subTest(example=path.name):
                self.assertNotIn('"version": "latest"', rendered)

    def test_agent_run_has_versioned_price_snapshot(self) -> None:
        payload = json.loads((ROOT / "examples" / "valid" / "agent-run.json").read_text(encoding="utf-8"))
        dependency_snapshot = payload["spec"]["resolved_dependencies"]["price_snapshot_ref"]
        usage_snapshot = payload["spec"]["usage"]["price_snapshot_ref"]
        self.assertRegex(dependency_snapshot["version"], r"^\d+\.\d+\.\d+")
        self.assertEqual(dependency_snapshot["digest"], usage_snapshot["digest"])

    def test_event_exposes_cloudevents_1_0_required_attributes(self) -> None:
        payload = json.loads((ROOT / "examples" / "valid" / "event.json").read_text(encoding="utf-8"))
        event = payload["spec"]
        self.assertEqual("1.0", event["specversion"])
        self.assertEqual(payload["metadata"]["id"], event["id"])
        for field in ("source", "type", "time", "datacontenttype", "dataschema", "data"):
            self.assertIn(field, event)

    def test_platform_error_codes_are_unique(self) -> None:
        vocabulary = json.loads((ROOT / "vocabularies" / "error-codes.json").read_text(encoding="utf-8"))
        codes = [item["code"] for item in vocabulary["codes"]]
        self.assertEqual(len(codes), len(set(codes)))
        expected = {
            json.loads(path.read_text(encoding="utf-8"))["expected_error_code"]
            for path in INVALID_FILES
        }
        self.assertTrue(expected.issubset(set(codes)))

    def test_unknown_root_field_is_rejected(self) -> None:
        payload = json.loads((ROOT / "examples" / "valid" / "task.json").read_text(encoding="utf-8"))
        payload["unknown"] = True
        with self.assertRaises(ValidationError):
            RESOURCE_MODELS["task"].model_validate(payload)

    def test_manifest_digests_match_generated_files(self) -> None:
        manifest = json.loads((ROOT / "contract-manifest.json").read_text(encoding="utf-8"))
        for item in manifest["generated_files"]:
            with self.subTest(path=item["path"]):
                digest = "sha256:" + hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()
                self.assertEqual(item["digest"], digest)

    def test_canonical_digest_is_deterministic(self) -> None:
        first = {"b": 2, "a": ["中文", 1]}
        second = {"a": ["中文", 1], "b": 2}
        self.assertEqual(canonical_json(first), canonical_json(second))
        self.assertEqual(canonical_sha256(first), canonical_sha256(second))

    def test_no_raw_secret_markers_in_examples(self) -> None:
        forbidden_literals = ("-----BEGIN PRIVATE KEY-----", "x-amz-signature=", "password=")
        provider_secret = re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b", re.IGNORECASE)
        for path in VALID_FILES:
            lowered = path.read_text(encoding="utf-8").lower()
            with self.subTest(example=path.name):
                for marker in forbidden_literals:
                    self.assertNotIn(marker.lower(), lowered)
                self.assertIsNone(provider_secret.search(lowered))


class PermissionAndIdempotencyTests(unittest.TestCase):
    def test_deny_has_absolute_precedence(self) -> None:
        self.assertEqual("deny", combine_permission_decisions(["allow", "require_approval", "deny"]))
        self.assertEqual("require_approval", combine_permission_decisions(["allow", "require_approval"]))
        self.assertEqual("allow", combine_permission_decisions(["allow", "allow"]))
        self.assertEqual("deny", combine_permission_decisions([]))

    def test_idempotency_keys_are_scope_sensitive(self) -> None:
        key_a = scoped_task_idempotency_key("ten_a", "api", "request-1")
        key_b = scoped_task_idempotency_key("ten_b", "api", "request-1")
        self.assertNotEqual(key_a, key_b)
        tool_a = scoped_tool_idempotency_key("tol_a", "resource:a", "request-1")
        tool_b = scoped_tool_idempotency_key("tol_a", "resource:b", "request-1")
        self.assertNotEqual(tool_a, tool_b)

    def test_unknown_tool_call_never_auto_retries(self) -> None:
        self.assertFalse(can_auto_retry(retryable=True, safe_to_retry=True, tool_allows_retry=True, state="unknown"))
        self.assertTrue(can_auto_retry(retryable=True, safe_to_retry=True, tool_allows_retry=True, state="failed"))

    def test_stale_fencing_token_cannot_commit(self) -> None:
        expires = datetime(2026, 8, 28, 1, 0, tzinfo=timezone.utc)
        now = datetime(2026, 8, 28, 0, 30, tzinfo=timezone.utc)
        self.assertTrue(lease_allows_commit(fencing_token=2, current_fencing_token=2, expires_at=expires, now=now))
        self.assertFalse(lease_allows_commit(fencing_token=1, current_fencing_token=2, expires_at=expires, now=now))
        self.assertFalse(lease_allows_commit(fencing_token=2, current_fencing_token=2, expires_at=expires, now=expires))


class ResolutionAndRunBoundaryTests(unittest.TestCase):
    def test_new_run_resolution_accepts_only_active_definitions(self) -> None:
        self.assertTrue(definition_is_resolvable(definition_phase="active", purpose="new_run"))
        self.assertFalse(definition_is_resolvable(definition_phase="deprecated", purpose="new_run"))
        self.assertFalse(definition_is_resolvable(definition_phase="blocked", purpose="new_run"))

    def test_resume_accepts_frozen_deprecated_but_not_blocked_or_archived(self) -> None:
        self.assertTrue(definition_is_resolvable(definition_phase="active", purpose="resume_run"))
        self.assertTrue(definition_is_resolvable(definition_phase="deprecated", purpose="resume_run"))
        self.assertFalse(definition_is_resolvable(definition_phase="blocked", purpose="resume_run"))
        self.assertFalse(definition_is_resolvable(definition_phase="archived", purpose="resume_run"))

    def test_unknown_resolution_purpose_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            definition_is_resolvable(definition_phase="active", purpose="migration")

    def test_dynamic_activation_history_is_append_only(self) -> None:
        first = [{"sequence": 1, "resource": "skill-a"}]
        appended = [*first, {"sequence": 2, "resource": "tool-a"}]
        rewritten = [{"sequence": 1, "resource": "skill-b"}]
        self.assertTrue(activation_history_is_append_only(first, appended))
        self.assertFalse(activation_history_is_append_only(first, rewritten))
        self.assertFalse(activation_history_is_append_only(appended, first))

    def test_declared_fallback_stays_in_same_run(self) -> None:
        self.assertEqual(
            "same_run_fallback",
            model_switch_boundary(
                run_phase="running",
                route_in_fallback_chain=True,
                trigger_error_allowed=True,
                frozen_dependencies_unchanged=True,
                policy_constraints_satisfied=True,
                budget_available=True,
            ),
        )

    def test_model_switch_outside_frozen_boundary_requires_new_run(self) -> None:
        base = {
            "run_phase": "running",
            "route_in_fallback_chain": True,
            "trigger_error_allowed": True,
            "frozen_dependencies_unchanged": True,
            "policy_constraints_satisfied": True,
            "budget_available": True,
        }
        for override in (
            {"run_phase": "failed"},
            {"route_in_fallback_chain": False},
            {"trigger_error_allowed": False},
            {"frozen_dependencies_unchanged": False},
            {"policy_constraints_satisfied": False},
            {"budget_available": False},
        ):
            with self.subTest(override=override):
                self.assertEqual("new_run_required", model_switch_boundary(**(base | override)))


class StateMachineTests(unittest.TestCase):
    def test_state_machine_files_match_code(self) -> None:
        for name, transitions in STATE_MACHINES.items():
            with self.subTest(machine=name):
                document = json.loads((ROOT / "state-machines" / f"{name}.json").read_text(encoding="utf-8"))
                self.assertEqual({state: list(targets) for state, targets in transitions.items()}, document["transitions"])

    def test_every_transition_targets_a_declared_state(self) -> None:
        for name, transitions in STATE_MACHINES.items():
            states = set(transitions)
            with self.subTest(machine=name):
                self.assertTrue(all(target in states for targets in transitions.values() for target in targets))

    def test_terminal_states_cannot_transition(self) -> None:
        for name, transitions in STATE_MACHINES.items():
            for state, targets in transitions.items():
                if targets:
                    continue
                with self.subTest(machine=name, state=state):
                    with self.assertRaises(StateTransitionError):
                        transition(name, state, next(iter(transitions)))

    def test_illegal_transition_is_rejected(self) -> None:
        with self.assertRaises(StateTransitionError):
            transition("task", "succeeded", "running")
        with self.assertRaises(StateTransitionError):
            transition("tool-call", "unknown", "executing")

    def test_legal_transition_requires_event(self) -> None:
        result = transition("agent-run", "created", "resolving")
        self.assertTrue(result.event_required)


if __name__ == "__main__":
    unittest.main()
