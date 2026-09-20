"""Offline tests for generation-faithfulness evaluation (pure, no real LLM)."""

import json

from presale.adapters.generation_eval import (
    classify_response,
    evaluate_adversarial,
    evaluate_generation,
    parse_judge,
    qa_golden,
    qa_golden_adversarial,
)


def test_parse_judge_extracts_numbers_and_clamps():
    text = (
        '{"faithfulness": 0.85, "answer_correctness": 1.2, '
        '"gold_correctness": 0.6, "unsupported_claims": ["X", "Y"]}'
    )
    parsed = parse_judge(text)
    assert parsed["faithfulness"] == 0.85
    assert parsed["answer_correctness"] == 1.0  # clamped
    assert parsed["gold_correctness"] == 0.6
    assert parsed["unsupported_claims"] == 2


def test_parse_judge_tolerates_malformed_or_fragmented():
    assert parse_judge("not json at all") == {
        "faithfulness": 0.0,
        "answer_correctness": 0.0,
        "gold_correctness": 0.0,
        "unsupported_claims": 0,
    }
    fragmented = (
        '评语：答案忠实。\n"faithfulness":0.6\n"answer_correctness":0.7\n'
        '"gold_correctness":0.5\n"unsupported_claims":[]'
    )
    parsed = parse_judge(fragmented)
    assert parsed["faithfulness"] == 0.6
    assert parsed["answer_correctness"] == 0.7
    assert parsed["unsupported_claims"] == 0


class _FakeEvidence:
    def __init__(self, content):
        self.content = content


class _FakeRetrievalResult:
    def __init__(self, contents):
        self.evidence_items = [_FakeEvidence(c) for c in contents]


class _FakeRetriever:
    def __init__(self, contents_by_product):
        self._map = contents_by_product

    def retrieve(self, question):
        return _FakeRetrievalResult(self._map.get(question.product_id, []))


def _fake_transport(base_url, model):
    def transport(**kwargs):
        prompt = kwargs["messages"][0]["content"]
        if "质检评审" in prompt:
            content = (
                '{"faithfulness": 1.0, "answer_correctness": 1.0, '
                '"gold_correctness": 1.0, "unsupported_claims": []}'
            )
        else:
            content = "这是一个仅基于证据生成的中文回答。"
        return {"choices": [{"message": {"content": content}}]}

    return transport


def test_evaluate_generation_aggregates_per_question():
    contents = {
        "product-001": ["紫外线防护系数 UPF50+"],
        "product-002": ["零下严寒仍能锁温"],
    }
    retriever = _FakeRetriever(contents)
    questions = [
        {"tenant_id": "tenant-demo", "product_id": "product-001", "query": "能防紫外线吗"},
        {"tenant_id": "tenant-demo", "product_id": "product-002", "query": "很冷冷穿够暖吗"},
    ]

    report = evaluate_generation(
        retriever,
        transport=_fake_transport("x", "y"),
        base_url="x",
        model="y",
        api_key="k",
        questions=questions,
    )

    assert report["n"] == 2
    assert report["mean_faithfulness"] == 1.0
    assert report["mean_answer_correctness"] == 1.0
    assert report["mean_gold_correctness"] == 1.0
    assert report["total_unsupported_claims"] == 0
    assert {p["product_id"] for p in report["per_question"]} == {"product-001", "product-002"}


def test_gold_correctness_catches_faithful_but_wrong():
    # A judge that says the answer is fully grounded (faithfulness=1.0) but wrong
    # vs the reference (gold_correctness low) must surface a divergence.
    def judge(**kwargs):
        prompt = kwargs["messages"][0]["content"]
        if "质检评审" in prompt:
            content = (
                '{"faithfulness": 1.0, "answer_correctness": 0.2, '
                '"gold_correctness": 0.2, "unsupported_claims": []}'
            )
        else:
            content = "可以退货，运费由买家承担。"
        return {"choices": [{"message": {"content": content}}]}

    retriever = _FakeRetriever({"product-001": ["本商品七天无理由退货"]})
    report = evaluate_generation(
        retriever,
        transport=judge,
        base_url="x",
        model="y",
        api_key="k",
        questions=[
            {
                "tenant_id": "tenant-demo",
                "product_id": "product-001",
                "query": "退货要钱吗",
                "gold": "本商品支持七天无理由退货。",
            }
        ],
    )

    row = report["per_question"][0]
    assert row["faithfulness"] == 1.0  # grounded in evidence
    assert row["gold_correctness"] == 0.2  # but wrong vs reference -> caught
    assert row["gold_correctness"] < row["faithfulness"]


def test_qa_golden_is_nonempty_and_wellformed():
    golden = qa_golden()
    assert len(golden) >= 5
    for item in golden:
        assert {"tenant_id", "product_id", "query"} <= set(item)


def test_qa_golden_adversarial_is_nonempty():
    golden = qa_golden_adversarial()
    assert len(golden) >= 3
    for item in golden:
        assert {"tenant_id", "product_id", "query"} <= set(item)


def test_classify_response_detects_refusal_markers():
    assert classify_response("这个问题我们无法确定，建议转人工复核。") == "withheld"
    assert classify_response("证据中未提供相关信息，无法回答。") == "withheld"
    assert (
        classify_response("根据现有信息，未提及能否单独购买，建议咨询官方客服确认。") == "withheld"
    )
    assert classify_response("可以开发票，请提供邮箱地址。") == "answered"


class _JudgeTransport:
    """Answer prompt -> a canned answer; judge prompt -> flags unsupported claims."""

    def __init__(self, answer: str, unsupported: int):
        self._answer = answer
        self._unsupported = unsupported

    def __call__(self, **kwargs):
        prompt = kwargs["messages"][0]["content"]
        if "质检评审" in prompt:
            content = json.dumps(
                {
                    "faithfulness": 0.2,
                    "answer_correctness": 0.3,
                    "gold_correctness": 0.4,
                    "unsupported_claims": ["x"] * self._unsupported,
                },
                ensure_ascii=False,
            )
        else:
            content = self._answer
        return {"choices": [{"message": {"content": content}}]}


class _EmptyRetriever:
    def retrieve(self, question):
        return _FakeRetrievalResult([])


def test_adversarial_counts_undetected_fabrication_when_judge_is_blind():
    # Assistant fabricates an answer (not withheld) and the judge fails to flag it.
    retriever = _EmptyRetriever()
    transport = _JudgeTransport(answer="可以开发票，请提供邮箱。", unsupported=0)

    report = evaluate_adversarial(
        retriever, transport=transport, base_url="x", model="y", api_key="k", sever_evidence=True
    )

    assert report["undetected_fabrications"] >= 1
    assert report["per_question"][0]["undetected_fabrication"] is True
    assert report["per_question"][0]["withheld"] is False


def test_adversarial_no_undetected_when_judge_flags_or_assistant_withholds():
    retriever = _EmptyRetriever()
    # Assistant fabricates but the judge flags it as unsupported -> not undetected.
    flagged = evaluate_adversarial(
        retriever,
        transport=_JudgeTransport(answer="可以开发票。", unsupported=2),
        base_url="x",
        model="y",
        api_key="k",
        sever_evidence=True,
    )
    assert flagged["undetected_fabrications"] == 0

    # Assistant withholds (grounded refusal) -> not undetected even if judge reports none.
    withheld = evaluate_adversarial(
        retriever,
        transport=_JudgeTransport(answer="无法确定，建议转人工复核。", unsupported=0),
        base_url="x",
        model="y",
        api_key="k",
        sever_evidence=True,
    )
    assert withheld["undetected_fabrications"] == 0
    assert all(r["withheld"] for r in withheld["per_question"])


def test_evaluate_end_to_end_runs_real_runner_and_judges():
    # Exercise the REAL PresaleQaRunner.ask (default deterministic generator +
    # DeterministicKnowledgeRetriever) with a faked judge transport — no Net/LLM.
    from presale.adapters.generation_eval import evaluate_end_to_end
    from presale.answer import PresaleAnswerGenerator
    from presale.knowledge import DeterministicKnowledgeRetriever, KnowledgeSource

    sources = [
        KnowledgeSource(
            source_id="src-001",
            version="2026.09.01",
            tenant_id="tenant-demo",
            product_id="product-001",
            status="published",
            fields={"spec": {"material": "防晒衣，能阻挡紫外线"}},
        )
    ]
    retriever = DeterministicKnowledgeRetriever(sources)
    generator = PresaleAnswerGenerator()
    transport = _fake_transport("x", "y")

    report = evaluate_end_to_end(
        retriever,
        sources=sources,
        generator=generator,
        transport=transport,
        base_url="x",
        model="y",
        api_key="k",
        questions=[
            {"tenant_id": "tenant-demo", "product_id": "product-001", "query": "能防紫外线吗"}
        ],
    )

    assert report["n"] == 1
    assert report["per_question"][0]["query"] == "能防紫外线吗"
    assert report["per_question"][0]["faithfulness"] == 1.0  # faked judge
    assert report["per_question"][0]["answer"]  # runner produced a draft
