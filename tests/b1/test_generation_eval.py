"""Offline tests for generation-faithfulness evaluation (pure, no real LLM)."""

from presale.adapters.generation_eval import (
    evaluate_generation,
    parse_judge,
    qa_golden,
)


def test_parse_judge_extracts_numbers_and_clamps():
    text = '{"faithfulness": 0.85, "answer_correctness": 1.2, "unsupported_claims": ["X", "Y"]}'
    parsed = parse_judge(text)
    assert parsed["faithfulness"] == 0.85
    assert parsed["answer_correctness"] == 1.0  # clamped
    assert parsed["unsupported_claims"] == 2


def test_parse_judge_tolerates_malformed_or_fragmented():
    assert parse_judge("not json at all") == {
        "faithfulness": 0.0,
        "answer_correctness": 0.0,
        "unsupported_claims": 0,
    }
    fragmented = (
        '评语：答案忠实。\n"faithfulness":0.6\n"answer_correctness":0.7\n"unsupported_claims":[]'
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
            content = '{"faithfulness": 1.0, "answer_correctness": 1.0, "unsupported_claims": []}'
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
    assert report["total_unsupported_claims"] == 0
    assert {p["product_id"] for p in report["per_question"]} == {"product-001", "product-002"}


def test_qa_golden_is_nonempty_and_wellformed():
    golden = qa_golden()
    assert len(golden) >= 5
    for item in golden:
        assert {"tenant_id", "product_id", "query"} <= set(item)
