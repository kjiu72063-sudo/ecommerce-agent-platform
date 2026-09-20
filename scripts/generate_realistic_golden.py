"""Generate realistic shopper-style queries with the real LLM, anchored to facts.

For each product, pick ``--per-product`` fact chunks (locators) and ask the LLM to
write a natural user question (casual, may contain fillers/typos/abbreviations) whose
answer is that specific fact. Each query is anchored to its target locator *by
construction* — the LLM is told the fact and asked to produce the question that the
fact answers. Output is a JSON list of ``(tenant, product, query, {locator})`` ready
to be curated into the retrieval golden set.

Usage:
    PRESALE_LLM_BASE_URL=... PRESALE_LLM_MODEL=... PRESALE_LLM_API_KEY=... \
        python scripts/generate_realistic_golden.py --per-product 2 --out /tmp/queries.json
"""

from __future__ import annotations

import argparse
import json
import os
import re

from presale.adapters.generation_eval import llm_config
from presale.adapters.openai_generator import default_transport
from presale.cli import load_catalog

# Locators we prefer to generate realistic queries for (fact chunks). description/
# features/README-ish keys are less crisp to anchor to a single answer.
PREFERRED = (
    "spec_",
    "care",
    "after_",
    "wash_",
    "extreme_",
    "transit",
    "range",
    "portion",
    "power_resume",
    "travel",
    "call_quality",
    "gaming_latency",
    "heartbeat",
    "swim_use",
    "newhome",
    "night_use",
    "wet_grip",
    "rough_ground",
    "spec_size",
    "spec_battery",
    "spec_waterproof",
    "spec_capacity",
    "spec_weight",
    "spec_power",
    "spec_auto",
    "spec_odor",
    "spec_zone",
    "spec_firmness",
    "spec_wheels",
    "spec_lock",
    "setup_time",
    "spec_milk",
    "spec_grind",
    "spec_noise",
    "spec_lumbar",
    "spec_recline",
    "wind_resist",
)


def _pick_locators(fields: dict) -> list[str]:
    picked = [k for k in fields if any(k.startswith(p) for p in PREFERRED)]
    return picked or list(fields.keys())


def _chat(prompt: str, base_url: str, model: str, api_key: str) -> str:
    completion = default_transport(
        api_key=api_key,
        base_url=base_url,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        timeout_s=float(os.environ.get("PRESALE_GEN_TIMEOUT_S", "60")),
    )
    return completion["choices"][0]["message"]["content"].strip()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate realistic golden queries via LLM.")
    parser.add_argument("--catalog", default="src/presale/data/dev_catalog.json")
    parser.add_argument("--per-product", type=int, default=2)
    parser.add_argument("--out", default="tests/fixtures/realistic_queries.json")
    args = parser.parse_args(argv)

    base_url, model, api_key = llm_config()
    rows: list[dict[str, str]] = []
    for source in load_catalog(args.catalog):
        for locator in _pick_locators(source.fields)[: args.per_product]:
            content = source.fields[locator]
            prompt = (
                "你是电商售前语料构建。用户正在咨询某商品，该商品有一条资料信息为："
                f"「{content}」。\n"
                "请用真实买家的口吻（可以带口语、省略、错别字、反问、语气词）写一句"
                "会引出这条信息作为答案的用户提问。\n"
                "要求：只输出这一句提问本身，不要解释、不要包含答案内容里的关键词照搬。"
            )
            query = _chat(prompt, base_url, model, api_key)
            query = re.sub(r"^[「“\"']+|[」”\"']+$", "", query).strip()
            rows.append(
                {
                    "tenant_id": source.tenant_id,
                    "product_id": source.product_id,
                    "query": query,
                    "locator": locator,
                }
            )
            print(json.dumps(rows[-1], ensure_ascii=False))

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)
    print(f"wrote {len(rows)} queries to {args.out}")


if __name__ == "__main__":
    main()
