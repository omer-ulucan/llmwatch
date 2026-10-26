"""
Tests for every evaluator, case scoring, and assertion validation.
"""

import pytest

from llmwatch.evals.evaluators import (
    AssertionConfigError,
    EvalContext,
    EvalInput,
    JudgeReply,
    cosine,
    effective_assertions,
    evaluate_case,
    model_family,
    parse_judge_reply,
    validate_assertion,
)
from llmwatch.evals.schema import (
    Assertion,
    SuiteDefinition,
    SuiteFormatError,
    parse_suite,
)


def A(type_, value=None, **cfg) -> Assertion:
    return Assertion(type=type_, value=value, **cfg)


async def run(assertion, output="", ctx=None, **inp):
    from llmwatch.evals.evaluators import EVALUATORS

    return await EVALUATORS[assertion.type](
        assertion, EvalInput(output=output, **inp), ctx or EvalContext()
    )


# ── exact_match ─────────────────────────────────────────────


async def test_exact_match_defaults_trim_and_collapse_whitespace():
    o = await run(A("exact_match", "Paris"), "  Paris \n")
    assert (o.score, o.passed) == (1.0, True)
    assert (await run(A("exact_match", "Paris is   big"), "Paris is big")).passed


async def test_exact_match_is_case_sensitive_by_default():
    o = await run(A("exact_match", "Paris"), "paris")
    assert (o.score, o.passed) == (0.0, False)
    assert "Expected 'Paris'" in o.reason
    assert (await run(A("exact_match", "Paris", case_sensitive=False), "paris")).passed


async def test_exact_match_ignore_punctuation():
    assert (
        await run(A("exact_match", "Paris", ignore_punctuation=True), "Paris.")
    ).passed
    assert not (await run(A("exact_match", "Paris"), "Paris.")).passed


async def test_exact_match_falls_back_to_expected():
    assert (await run(A("exact_match"), "billing", expected="billing")).passed
    o = await run(A("exact_match"), "billing")
    assert o.error and not o.passed


# ── contains / not_contains ─────────────────────────────────


async def test_contains_single_and_case_options():
    assert (await run(A("contains", "refund"), "issue a refund now")).passed
    assert not (await run(A("contains", "Refund"), "issue a refund")).passed
    assert (
        await run(A("contains", "Refund", case_sensitive=False), "issue a refund")
    ).passed


async def test_contains_list_all_gives_partial_credit():
    o = await run(A("contains", ["alpha", "beta", "gamma", "delta"]), "alpha and beta")
    assert o.score == 0.5
    assert not o.passed
    assert "'gamma'" in o.reason


async def test_contains_list_any():
    o = await run(A("contains", ["cat", "dog"], mode="any"), "a dog")
    assert (o.score, o.passed) == (1.0, True)


async def test_not_contains():
    assert (await run(A("not_contains", ["sorry", "as an AI"]), "Here you go")).passed
    o = await run(A("not_contains", ["sorry", "as an AI"]), "Sorry, as an AI I can't")
    assert o.passed is False
    assert o.score == 0.5  # "sorry" is case-sensitive, so only one was found


# ── regex ───────────────────────────────────────────────────


async def test_regex_search_and_flags():
    assert (await run(A("regex", r"\d{3}-\d{4}"), "call 555-1234")).passed
    assert not (await run(A("regex", r"^ok$"), "OK")).passed
    assert (await run(A("regex", r"^ok$", flags="i"), "OK")).passed


def test_invalid_regex_rejected_at_validation():
    with pytest.raises(AssertionConfigError, match="Invalid regex"):
        validate_assertion(A("regex", "(unclosed"))
    with pytest.raises(AssertionConfigError, match="flag"):
        validate_assertion(A("regex", "x", flags="z"))


# ── JSON ────────────────────────────────────────────────────


async def test_json_valid_accepts_code_fences():
    assert (await run(A("json_valid"), '```json\n{"a": 1}\n```')).passed
    o = await run(A("json_valid"), "{not json}")
    assert not o.passed
    assert "Invalid JSON" in o.reason


SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"enum": ["billing", "bug"]},
        "confidence": {"type": "number"},
    },
    "required": ["label"],
}


async def test_json_schema():
    assert (
        await run(A("json_schema", SCHEMA), '{"label": "bug", "confidence": 0.9}')
    ).passed
    o = await run(A("json_schema", SCHEMA), '{"label": "other"}')
    assert not o.passed
    assert "label" in o.reason


def test_invalid_json_schema_rejected_at_validation():
    with pytest.raises(AssertionConfigError, match="Invalid JSON schema"):
        validate_assertion(A("json_schema", {"type": "not-a-type"}))
    with pytest.raises(AssertionConfigError):
        validate_assertion(A("json_schema", "nope"))


# ── similarity ──────────────────────────────────────────────


def test_cosine_known_values():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert cosine([1, 1], [1, 0]) == pytest.approx(1 / 2**0.5)


async def test_similarity_uses_the_embedding_model():
    calls = []

    async def embed(model, texts):
        calls.append((model, texts))
        return [[1.0, 1.0], [1.0, 0.0]]

    ctx = EvalContext(embed=embed)
    o = await run(
        A("similarity", "reference", model="emb", threshold=0.7), "answer", ctx
    )
    assert o.score == pytest.approx(0.7071, abs=1e-4)
    assert o.passed
    assert calls == [("emb", ["answer", "reference"])]
    strict = await run(
        A("similarity", "reference", model="emb", threshold=0.9), "answer", ctx
    )
    assert not strict.passed


async def test_similarity_without_embedding_model_is_an_error():
    o = await run(A("similarity", "x"), "y", EvalContext())
    assert o.error and not o.passed


# ── llm_judge ───────────────────────────────────────────────


def _judge(content, model_id="judge-model", label="J/judge-model"):
    calls = []

    async def judge(model_ref, messages, params):
        calls.append((model_ref, messages, params))
        return JudgeReply(content=content, model_id=model_id, label=label)

    return judge, calls


async def test_llm_judge_scores_with_temperature_zero_and_json():
    judge, calls = _judge('{"reasoning": "Correct and concise.", "score": 8}')
    o = await run(
        A("llm_judge", "Is the answer correct?", model="J/judge-model"),
        "Paris",
        EvalContext(judge=judge),
        prompt="Capital of France?",
        expected="Paris",
        candidate_model="gpt-x",
    )
    assert o.score == pytest.approx(0.8)
    assert o.passed  # default threshold 0.7
    assert "Correct and concise" in o.reason
    model_ref, messages, params = calls[0]
    assert model_ref == "J/judge-model"
    assert params["temperature"] == 0
    assert params["response_format"] == {"type": "json_object"}
    assert "Is the answer correct?" in messages[1]["content"]
    assert "REFERENCE ANSWER:\nParis" in messages[1]["content"]
    assert not o.warnings


async def test_llm_judge_threshold():
    judge, _ = _judge('{"reasoning": "meh", "score": 5}')
    o = await run(
        A("llm_judge", "rubric", threshold=0.6), "x", EvalContext(judge=judge)
    )
    assert not o.passed


async def test_llm_judge_warns_when_judge_and_candidate_share_a_family():
    judge, _ = _judge('{"reasoning": "ok", "score": 9}', model_id="gpt-4o")
    o = await run(
        A("llm_judge", "rubric"),
        "x",
        EvalContext(judge=judge),
        candidate_model="gpt-4o-mini",
    )
    assert o.warnings and "same model family" in o.warnings[0]


@pytest.mark.parametrize(
    "reply",
    ["no json here", '{"score": "high"}', '{"score": 42}', '{"reasoning": "x"}'],
)
async def test_llm_judge_unparseable_reply_is_an_error(reply):
    judge, _ = _judge(reply)
    o = await run(A("llm_judge", "rubric"), "x", EvalContext(judge=judge))
    assert o.error and not o.passed and o.score == 0


async def test_llm_judge_call_failure_is_an_error():
    async def judge(*args):
        raise RuntimeError("rate limited")

    o = await run(A("llm_judge", "rubric"), "x", EvalContext(judge=judge))
    assert o.error and "rate limited" in o.reason


def test_parse_judge_reply_tolerates_fences_and_prose():
    assert parse_judge_reply(
        'Sure!\n```json\n{"score": 10, "reasoning": "perfect"}\n```'
    ) == (
        1.0,
        "perfect",
    )


@pytest.mark.parametrize(
    "model_id,family",
    [
        ("gpt-4o-mini", "gpt"),
        ("models/gemini-2.5-pro", "gemini"),
        ("qwen3.5:0.8b", "qwen"),
        ("meta-llama/Llama-3.1-8B", "llama"),
        ("claude-sonnet-4", "claude"),
    ],
)
def test_model_family(model_id, family):
    assert model_family(model_id) == family


# ── latency / cost ──────────────────────────────────────────


async def test_latency_under():
    assert (await run(A("latency_under", 500), latency_ms=499.0)).passed
    assert not (await run(A("latency_under", 500), latency_ms=501.0)).passed


async def test_cost_under():
    assert (await run(A("cost_under", 0.01), cost_usd=0.005)).passed
    assert not (await run(A("cost_under", 0.01), cost_usd=0.02)).passed


async def test_cost_under_fails_for_unpriced_models():
    o = await run(A("cost_under", 1.0), cost_usd=None)
    assert not o.passed and o.error
    assert "no price" in o.reason


@pytest.mark.parametrize("value", [-1, "cheap", None])
def test_latency_and_cost_need_a_non_negative_number(value):
    with pytest.raises(AssertionConfigError):
        validate_assertion(A("cost_under", value))


# ── Case scoring ────────────────────────────────────────────


async def test_case_score_is_the_weighted_mean_and_all_must_pass():
    assertions = [
        A("contains", "a", weight=3),
        A("contains", "zzz", weight=1),
    ]
    score, passed, outcomes = await evaluate_case(
        assertions, EvalInput(output="abc"), EvalContext()
    )
    assert score == pytest.approx(0.75)
    assert passed is False
    assert [o.passed for o in outcomes] == [True, False]
    assert outcomes[0].to_dict()["weight"] == 3


async def test_scores_are_clamped_to_unit_interval():
    async def embed(model, texts):
        return [[1.0, 0.0], [-1.0, 0.0]]  # cosine -1

    o = await run(A("similarity", "x", model="e"), "y", EvalContext(embed=embed))
    assert o.score == 0.0


def test_bare_expected_means_exact_match():
    suite = SuiteDefinition(
        prompt="{{q}}", name="s", cases=[{"vars": {"q": 1}, "expected": "x"}]
    )
    effective = effective_assertions(suite, [], "x")
    assert [a.type for a in effective] == ["exact_match"]


def test_defaults_plus_bare_expected_still_compares_the_answer():
    suite = SuiteDefinition.model_validate(
        {
            "name": "s",
            "prompt": "{{q}}",
            "assert": [{"type": "latency_under", "value": 5000}],
            "cases": [{"vars": {"q": 1}, "expected": "x"}],
        }
    )
    effective = effective_assertions(suite, [], "x")
    assert [a.type for a in effective] == ["latency_under", "exact_match"]


# ── Suite validation ────────────────────────────────────────


def test_unknown_assertion_type_rejected_in_suites():
    with pytest.raises(SuiteFormatError, match="Unknown assertion type 'smells_good'"):
        parse_suite("name: s\nprompt: hi\ncases:\n  - assert: [{type: smells_good}]\n")


def test_case_without_any_check_rejected():
    with pytest.raises(SuiteFormatError, match="no assertions and no expected"):
        parse_suite("name: s\nprompt: hi\ncases:\n  - vars: {}\n")


def test_judge_rubric_required():
    with pytest.raises(SuiteFormatError, match="llm_judge needs a `value`"):
        parse_suite("name: s\nprompt: hi\ncases:\n  - assert: [{type: llm_judge}]\n")


def test_threshold_bounds_validated():
    with pytest.raises(AssertionConfigError, match="threshold"):
        validate_assertion(A("llm_judge", "r", threshold=7))
