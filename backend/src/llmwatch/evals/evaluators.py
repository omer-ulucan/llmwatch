"""
Module: evaluators.py
Purpose: Pluggable checks that score one model output.
WHY: Every evaluator answers the same three questions, so results are comparable and
explainable: a score in [0, 1], pass/fail, and a human-readable reason. A case's
score is the weighted mean of its assertion scores; it passes when every assertion
passes.

Types (assertion `type`):
  exact_match     equals `value` (or the case's `expected`); normalisation options
  contains        output contains `value` (string or list; mode all|any)
  not_contains    output contains none of `value`
  regex           output matches the pattern `value` (flags: i, m, s)
  json_valid      output is JSON (```json fences allowed)
  json_schema     output is JSON valid against the schema in `value`
  similarity      embedding cosine similarity to `value`/`expected` >= threshold
  llm_judge       a judge model grades the output against the rubric in `value`
  latency_under   response latency <= `value` milliseconds
  cost_under      response cost <= `value` USD (fails if the model is unpriced)

Model-backed evaluators (similarity, llm_judge) call models through the EvalContext
the runner provides, so tests can swap in fakes and runs can cache the calls.
"""

import json
import math
import re
import string
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from llmwatch.evals.schema import Assertion, SuiteDefinition

MAX_EVAL_CHARS = 100_000


@dataclass
class EvalInput:
    output: str
    expected: str | None = None
    vars: dict[str, Any] = field(default_factory=dict)
    # The rendered prompt the candidate saw (for llm_judge).
    prompt: str = ""
    latency_ms: float = 0.0
    # None when the candidate model has no price set.
    cost_usd: float | None = 0.0
    # The candidate model's provider model id (for judge family warnings).
    candidate_model: str = ""


@dataclass
class EvalOutcome:
    type: str
    score: float
    passed: bool
    reason: str
    weight: float = 1.0
    warnings: list[str] = field(default_factory=list)
    # True when the evaluator itself couldn't run (judge failure, missing config).
    error: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = {
            "type": self.type,
            "score": round(self.score, 6),
            "passed": self.passed,
            "reason": self.reason,
            "weight": self.weight,
        }
        if self.warnings:
            data["warnings"] = self.warnings
        if self.error:
            data["error"] = True
        return data


@dataclass
class JudgeReply:
    content: str
    model_id: str
    label: str


# judge(model_ref, messages, params) -> JudgeReply
JudgeFn = Callable[[str, list[dict[str, str]], dict[str, Any]], Awaitable[JudgeReply]]
# embed(model_ref, texts) -> vectors
EmbedFn = Callable[[str, list[str]], Awaitable[list[list[float]]]]


@dataclass
class EvalContext:
    judge: JudgeFn | None = None
    embed: EmbedFn | None = None
    default_judge_model: str = "default"
    default_embedding_model: str | None = None


class AssertionConfigError(ValueError):
    """An assertion's configuration is invalid (raised at suite validation)."""


# ── Helpers ─────────────────────────────────────────────────


def _normalize(text: str, cfg: dict[str, Any]) -> str:
    if cfg.get("trim", True):
        text = text.strip()
    if cfg.get("normalize_whitespace", True):
        text = re.sub(r"\s+", " ", text)
    if not cfg.get("case_sensitive", True):
        text = text.casefold()
    if cfg.get("ignore_punctuation", False):
        text = text.translate(str.maketrans("", "", string.punctuation))
    return text


def _target(a: Assertion, inp: EvalInput) -> Any:
    return a.value if a.value is not None else inp.expected


def _strip_fences(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return (match.group(1) if match else text).strip()


def _outcome(
    a: Assertion, score: float, passed: bool, reason: str, **kw
) -> EvalOutcome:
    return EvalOutcome(
        a.type, max(0.0, min(1.0, score)), passed, reason, weight=a.weight, **kw
    )


def _regex_flags(spec: str) -> int:
    flags = 0
    for ch in spec or "":
        if ch == "i":
            flags |= re.IGNORECASE
        elif ch == "m":
            flags |= re.MULTILINE
        elif ch == "s":
            flags |= re.DOTALL
        else:
            raise AssertionConfigError(f"Unknown regex flag {ch!r} (use i, m, s)")
    return flags


def model_family(model_id: str) -> str:
    """Rough model family from a model id, e.g. "gpt-4o-mini" -> "gpt",
    "models/gemini-2.5-pro" -> "gemini", "qwen3.5:0.8b" -> "qwen"."""
    name = model_id.lower().rsplit("/", 1)[-1]
    match = re.match(r"[a-z]+", name)
    return match.group(0) if match else name


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("Vectors must be non-empty and the same length")
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


# ── Evaluators ──────────────────────────────────────────────


async def _exact_match(a: Assertion, inp: EvalInput, ctx: EvalContext) -> EvalOutcome:
    target = _target(a, inp)
    if target is None:
        return _outcome(
            a, 0, False, "No value or expected output to compare", error=True
        )
    cfg = a.config()
    ok = _normalize(inp.output, cfg) == _normalize(str(target), cfg)
    return _outcome(
        a, 1.0 if ok else 0.0, ok, "Exact match" if ok else f"Expected {str(target)!r}"
    )


def _needles(a: Assertion, inp: EvalInput) -> list[str]:
    target = _target(a, inp)
    if target is None:
        return []
    return [str(t) for t in target] if isinstance(target, list) else [str(target)]


async def _contains(a: Assertion, inp: EvalInput, ctx: EvalContext) -> EvalOutcome:
    needles = _needles(a, inp)
    if not needles:
        return _outcome(a, 0, False, "No value to look for", error=True)
    cfg = a.config()
    hay = inp.output if cfg.get("case_sensitive", True) else inp.output.casefold()
    found = [
        n
        for n in needles
        if (n if cfg.get("case_sensitive", True) else n.casefold()) in hay
    ]
    missing = [n for n in needles if n not in found]
    mode = cfg.get("mode", "all")
    passed = bool(found) if mode == "any" else not missing
    score = (1.0 if found else 0.0) if mode == "any" else len(found) / len(needles)
    reason = "Found all" if not missing else f"Missing: {', '.join(map(repr, missing))}"
    if mode == "any" and found:
        reason = f"Found {found[0]!r}"
    return _outcome(a, score, passed, reason)


async def _not_contains(a: Assertion, inp: EvalInput, ctx: EvalContext) -> EvalOutcome:
    needles = _needles(a, inp)
    if not needles:
        return _outcome(a, 0, False, "No value to look for", error=True)
    cfg = a.config()
    sensitive = cfg.get("case_sensitive", True)
    hay = inp.output if sensitive else inp.output.casefold()
    present = [n for n in needles if (n if sensitive else n.casefold()) in hay]
    passed = not present
    return _outcome(
        a,
        1 - len(present) / len(needles),
        passed,
        "None present"
        if passed
        else f"Found forbidden: {', '.join(map(repr, present))}",
    )


async def _regex(a: Assertion, inp: EvalInput, ctx: EvalContext) -> EvalOutcome:
    pattern = re.compile(str(a.value), _regex_flags(a.config().get("flags", "")))
    # WHY: Bound the text a user-supplied pattern runs over.
    match = pattern.search(inp.output[:MAX_EVAL_CHARS])
    return _outcome(
        a,
        1.0 if match else 0.0,
        bool(match),
        f"Matched {match.group(0)[:80]!r}" if match else f"No match for /{a.value}/",
    )


def _parse_json(text: str) -> tuple[Any, str | None]:
    try:
        return json.loads(_strip_fences(text)), None
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}"


async def _json_valid(a: Assertion, inp: EvalInput, ctx: EvalContext) -> EvalOutcome:
    _, error = _parse_json(inp.output)
    return _outcome(a, 0.0 if error else 1.0, error is None, error or "Valid JSON")


async def _json_schema(a: Assertion, inp: EvalInput, ctx: EvalContext) -> EvalOutcome:
    import jsonschema

    data, error = _parse_json(inp.output)
    if error:
        return _outcome(a, 0, False, error)
    validator = jsonschema.Draft202012Validator(a.value)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if not errors:
        return _outcome(a, 1, True, "Matches the schema")
    first = errors[0]
    where = "/".join(str(p) for p in first.path) or "(root)"
    return _outcome(
        a, 0, False, f"{len(errors)} schema error(s); at {where}: {first.message}"
    )


async def _similarity(a: Assertion, inp: EvalInput, ctx: EvalContext) -> EvalOutcome:
    target = _target(a, inp)
    if target is None:
        return _outcome(
            a, 0, False, "No value or expected output to compare", error=True
        )
    cfg = a.config()
    model = cfg.get("model") or ctx.default_embedding_model
    if ctx.embed is None or not model:
        return _outcome(
            a, 0, False, "similarity needs an embedding `model`", error=True
        )
    threshold = float(cfg.get("threshold", 0.8))
    try:
        vectors = await ctx.embed(model, [inp.output[:MAX_EVAL_CHARS], str(target)])
        score = cosine(vectors[0], vectors[1])
    except Exception as exc:
        return _outcome(a, 0, False, f"Embedding failed: {exc}", error=True)
    passed = score >= threshold
    return _outcome(
        a, score, passed, f"Cosine similarity {score:.3f} (threshold {threshold})"
    )


JUDGE_SYSTEM = """You are a strict, impartial evaluator. Grade the RESPONSE against the
RUBRIC. Judge only what the rubric asks; ignore style unless the rubric mentions it.
Reply with a single JSON object and nothing else:
{"reasoning": "<one or two sentences>", "score": <integer 0-10>}"""

JUDGE_USER = """RUBRIC:
{rubric}

INPUT GIVEN TO THE MODEL:
{prompt}
{expected}
RESPONSE TO GRADE:
{output}"""


def parse_judge_reply(text: str) -> tuple[float, str]:
    """(score in [0, 1], reasoning) from the judge's JSON. Raises ValueError."""
    candidate = _strip_fences(text)
    match = re.search(r"\{.*\}", candidate, re.DOTALL)
    if not match:
        raise ValueError("no JSON object in the judge's reply")
    data = json.loads(match.group(0))
    raw = data.get("score")
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise ValueError("judge reply has no numeric score")
    if not 0 <= raw <= 10:
        raise ValueError(f"judge score {raw} is outside 0-10")
    return float(raw) / 10.0, str(data.get("reasoning", "")).strip()


async def _llm_judge(a: Assertion, inp: EvalInput, ctx: EvalContext) -> EvalOutcome:
    if ctx.judge is None:
        return _outcome(a, 0, False, "No judge is available", error=True)
    cfg = a.config()
    model_ref = cfg.get("model") or ctx.default_judge_model
    threshold = float(cfg.get("threshold", 0.7))
    expected = f"\nREFERENCE ANSWER:\n{inp.expected}\n" if inp.expected else ""
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {
            "role": "user",
            "content": JUDGE_USER.format(
                rubric=a.value,
                prompt=inp.prompt[:20_000],
                expected=expected,
                output=inp.output[:MAX_EVAL_CHARS],
            ),
        },
    ]
    try:
        reply = await ctx.judge(
            model_ref,
            messages,
            {"temperature": 0, "response_format": {"type": "json_object"}},
        )
    except Exception as exc:
        return _outcome(a, 0, False, f"Judge call failed: {exc}", error=True)

    warnings = []
    if inp.candidate_model and model_family(reply.model_id) == model_family(
        inp.candidate_model
    ):
        warnings.append(
            f"Judge ({reply.label}) is from the same model family as the candidate; "
            "self-preference can inflate scores. Consider a different judge."
        )
    try:
        score, reasoning = parse_judge_reply(reply.content)
    except (ValueError, json.JSONDecodeError) as exc:
        return _outcome(
            a,
            0,
            False,
            f"Judge reply could not be parsed ({exc}): {reply.content[:200]!r}",
            warnings=warnings,
            error=True,
        )
    passed = score >= threshold
    return _outcome(
        a,
        score,
        passed,
        f"Judge score {score * 10:g}/10: {reasoning}",
        warnings=warnings,
    )


async def _latency_under(a: Assertion, inp: EvalInput, ctx: EvalContext) -> EvalOutcome:
    limit = float(a.value)
    ok = inp.latency_ms <= limit
    return _outcome(
        a, 1.0 if ok else 0.0, ok, f"{inp.latency_ms:.0f} ms (limit {limit:g} ms)"
    )


async def _cost_under(a: Assertion, inp: EvalInput, ctx: EvalContext) -> EvalOutcome:
    limit = float(a.value)
    if inp.cost_usd is None:
        # WHY: Unknown cost must not count as cheap.
        return _outcome(
            a, 0, False, "Cost unknown: the model has no price set", error=True
        )
    ok = inp.cost_usd <= limit
    return _outcome(
        a, 1.0 if ok else 0.0, ok, f"${inp.cost_usd:.6f} (limit ${limit:g})"
    )


Evaluator = Callable[[Assertion, EvalInput, EvalContext], Awaitable[EvalOutcome]]

EVALUATORS: dict[str, Evaluator] = {
    "exact_match": _exact_match,
    "contains": _contains,
    "not_contains": _not_contains,
    "regex": _regex,
    "json_valid": _json_valid,
    "json_schema": _json_schema,
    "similarity": _similarity,
    "llm_judge": _llm_judge,
    "latency_under": _latency_under,
    "cost_under": _cost_under,
}

# Evaluators that need `value` (others can fall back to the case's expected output).
_VALUE_REQUIRED = {"regex", "json_schema", "llm_judge", "latency_under", "cost_under"}


def validate_assertion(a: Assertion) -> None:
    """Rejects unknown types and broken configuration before a run starts."""
    if a.type not in EVALUATORS:
        raise AssertionConfigError(
            f"Unknown assertion type {a.type!r}; use one of: {', '.join(EVALUATORS)}"
        )
    if a.type in _VALUE_REQUIRED and a.value is None:
        raise AssertionConfigError(f"{a.type} needs a `value`")
    cfg = a.config()
    if a.type == "regex":
        try:
            re.compile(str(a.value), _regex_flags(cfg.get("flags", "")))
        except re.error as exc:
            raise AssertionConfigError(f"Invalid regex {a.value!r}: {exc}") from exc
        if len(str(a.value)) > 1000:
            raise AssertionConfigError("Regex patterns are limited to 1000 characters")
    elif a.type == "json_schema":
        import jsonschema

        if not isinstance(a.value, dict):
            raise AssertionConfigError(
                "json_schema `value` must be a JSON schema object"
            )
        try:
            jsonschema.Draft202012Validator.check_schema(a.value)
        except jsonschema.SchemaError as exc:
            raise AssertionConfigError(f"Invalid JSON schema: {exc.message}") from exc
    elif a.type in ("latency_under", "cost_under"):
        try:
            if float(a.value) < 0:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise AssertionConfigError(
                f"{a.type} `value` must be a non-negative number"
            ) from exc
    elif a.type in ("similarity", "llm_judge") and "threshold" in cfg:
        try:
            if not 0 <= float(cfg["threshold"]) <= 1:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise AssertionConfigError(
                f"{a.type} `threshold` must be between 0 and 1"
            ) from exc
    elif a.type in ("contains", "not_contains") and cfg.get("mode", "all") not in (
        "all",
        "any",
    ):
        raise AssertionConfigError("contains `mode` must be all or any")


def validate_definition(definition: SuiteDefinition) -> list[str]:
    """Problems with a suite's assertions (empty list when valid)."""
    problems: list[str] = []
    for a in definition.default_assertions:
        try:
            validate_assertion(a)
        except AssertionConfigError as exc:
            problems.append(f"suite assertion: {exc}")
    for case in definition.cases:
        for a in case.assertions:
            try:
                validate_assertion(a)
            except AssertionConfigError as exc:
                problems.append(f"case {case.id!r}: {exc}")
        if (
            not case.assertions
            and not definition.default_assertions
            and case.expected is None
        ):
            problems.append(
                f"case {case.id!r} has no assertions and no expected output to compare"
            )
    return problems


def effective_assertions(
    definition: SuiteDefinition, case_assertions: list[Assertion], expected: str | None
) -> list[Assertion]:
    """Suite defaults + the case's own; a bare `expected` means exact_match."""
    assertions = list(definition.default_assertions) + list(case_assertions)
    if (
        not case_assertions
        and expected is not None
        and not any(
            a.type in ("exact_match", "contains", "similarity", "llm_judge")
            for a in assertions
        )
    ):
        assertions.append(Assertion(type="exact_match"))
    return assertions


async def evaluate_case(
    assertions: list[Assertion], inp: EvalInput, ctx: EvalContext
) -> tuple[float, bool, list[EvalOutcome]]:
    """Runs every assertion: (weighted score, passed, outcomes)."""
    outcomes = [await EVALUATORS[a.type](a, inp, ctx) for a in assertions]
    if not outcomes:
        return 0.0, False, []
    total_weight = sum(o.weight for o in outcomes)
    score = sum(o.score * o.weight for o in outcomes) / total_weight
    return score, all(o.passed for o in outcomes), outcomes
