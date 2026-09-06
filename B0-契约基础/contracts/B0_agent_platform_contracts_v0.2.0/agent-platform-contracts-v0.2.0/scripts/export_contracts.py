#!/usr/bin/env python3
"""Generate deterministic schemas, examples, state machines, and a manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from agent_platform_contracts.models import COMMON_MODELS, RESOURCE_MODELS
from agent_platform_contracts.sample_data import invalid_examples, valid_examples
from agent_platform_contracts.state_machines import STATE_MACHINES, TERMINAL_STATES


ROOT = Path(__file__).resolve().parents[1]
DEFINITION_NAMES = {
    "agent-spec",
    "skill-manifest",
    "tool-manifest",
    "prompt-package",
    "model-policy",
    "context-policy",
    "loop-profile",
    "permission-profile",
}


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    path.write_text(rendered, encoding="utf-8")


def schema_for(name: str, model: type) -> dict[str, Any]:
    schema = model.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://schemas.agent-platform.local/v1alpha1/{name}.schema.json"
    schema["x-contract-version"] = "0.2.0"
    schema["x-source-model"] = f"agent_platform_contracts.models.{model.__name__}"
    return schema


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    generated: list[Path] = []
    for name, model in COMMON_MODELS.items():
        path = ROOT / "schemas" / "common" / f"{name}.schema.json"
        dump_json(path, schema_for(name, model))
        generated.append(path)

    for name, model in RESOURCE_MODELS.items():
        group = "definitions" if name in DEFINITION_NAMES else "runtime"
        path = ROOT / "schemas" / group / f"{name}.schema.json"
        dump_json(path, schema_for(name, model))
        generated.append(path)

    valid = valid_examples()
    invalid = invalid_examples()
    for name, payload in valid.items():
        path = ROOT / "examples" / "valid" / f"{name}.json"
        dump_json(path, payload)
        generated.append(path)
    for name, case in invalid.items():
        path = ROOT / "examples" / "invalid" / f"{name}.json"
        dump_json(path, case)
        generated.append(path)

    example_index = {
        "contract_version": "0.2.0",
        "valid": {name: f"valid/{name}.json" for name in sorted(valid)},
        "invalid": {name: {"path": f"invalid/{name}.json", "target_model": invalid[name]["target_model"], "expected_error_code": invalid[name]["expected_error_code"]} for name in sorted(invalid)},
    }
    index_path = ROOT / "examples" / "index.json"
    dump_json(index_path, example_index)
    generated.append(index_path)

    for name, transitions in STATE_MACHINES.items():
        document = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "machine": name,
            "initial_state": next(iter(transitions)),
            "terminal_states": sorted(TERMINAL_STATES[name]),
            "transitions": {state: list(targets) for state, targets in transitions.items()},
            "transition_event_required": True,
        }
        path = ROOT / "state-machines" / f"{name}.json"
        dump_json(path, document)
        generated.append(path)

    manifest = {
        "contract_version": "0.2.0",
        "schema_dialect": "https://json-schema.org/draft/2020-12/schema",
        "api_version": "agent-platform/v1alpha1",
        "generated_files": [
            {"path": path.relative_to(ROOT).as_posix(), "digest": sha256_file(path)}
            for path in sorted(generated)
        ],
    }
    dump_json(ROOT / "contract-manifest.json", manifest)


if __name__ == "__main__":
    main()
