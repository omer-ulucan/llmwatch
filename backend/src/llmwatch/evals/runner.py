"""
Module: runner.py (evals)
Purpose: Runs an eval suite version against a model "variant" and stores the results.
WHY: The runner turns (cases x repeats) into model calls and scored results while
staying polite and reproducible:

  - bounded concurrency per run, plus per-provider throttling (limiter.py)
  - retries with exponential backoff and full jitter for retryable errors (429, 5xx,
    timeouts), honouring Retry-After; other errors fail the item immediately
  - a content-addressed response cache, so re-runs are free and identical
  - prices are frozen on the run when it is created; costs are computed from that
    snapshot, so later price edits don't rewrite history
  - every item is committed as it finishes: an interrupted run resumes where it
    stopped, and a cancelled run keeps what it already did

Item failures (template errors, exhausted retries) are stored as failed results with
score 0, so comparisons count them instead of quietly dropping hard cases.
"""

import asyncio
import random
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update

from llmwatch.config import logger, settings
from llmwatch.db.engine import get_sessionmaker
from llmwatch.db.models import EvalCase, EvalResult, EvalRun, Model, Provider
from llmwatch.evals import cache, limiter
from llmwatch.evals.evaluators import (
    EvalContext,
    EvalInput,
    JudgeReply,
    effective_assertions,
    evaluate_case,
)
from llmwatch.evals.messages import build_messages
from llmwatch.evals.schema import Assertion, CaseDefinition
from llmwatch.evals.suites import LoadedSuite, load_suite, load_version_by_id
from llmwatch.evals.template import TemplateError
from llmwatch.exceptions import ValidationException
from llmwatch.llm import ChatResult, LLMClient, LLMError, Usage, compute_cost
from llmwatch.llm.reasoning import reasoning_controls
from llmwatch.providers import service as provider_service
from llmwatch.providers.models import resolve_model

ACTIVE_STATUSES = ("pending", "running")
FINAL_STATUSES = ("completed", "failed", "cancelled", "interrupted")


@dataclass
class VariantSpec:
    model: str
    params: dict[str, Any] = field(default_factory=dict)
    label: str = ""
    # Let reasoning models think (off by default, as in chat).
    thinking: bool = False


async def create_runs(
    session,
    workspace_id: str,
    *,
    suite_id: str,
    variants: list[VariantSpec],
    version: int | None = None,
    repeats: int = 1,
    concurrency: int = 4,
    judge_model: str | None = None,
    embedding_model: str | None = None,
    use_cache: bool = True,
    created_by: str | None = None,
) -> list[EvalRun]:
    """Creates one pending run per variant (sharing a group id). Resolves every model
    up front, so a typo fails the request instead of a background run."""
    loaded = await load_suite(session, workspace_id, suite_id, version)
    if judge_model:
        await resolve_model(session, workspace_id, judge_model)
    if embedding_model:
        await resolve_model(session, workspace_id, embedding_model)
    group_id = str(uuid.uuid4()) if len(variants) > 1 else None
    total = len(loaded.cases) * repeats
    runs = []
    for spec in variants:
        resolved = await resolve_model(session, workspace_id, spec.model)
        m, p = resolved.model, resolved.provider
        run = EvalRun(
            workspace_id=workspace_id,
            suite_id=loaded.suite.id,
            suite_version_id=loaded.version.id,
            group_id=group_id,
            label=spec.label or resolved.label,
            status="pending",
            model_ref_id=m.id,
            variant={
                "model": spec.model,
                "model_label": resolved.label,
                "model_id": m.model_id,
                "provider": p.name,
                "provider_id": p.id,
                "params": {k: v for k, v in spec.params.items() if v is not None},
                "thinking": spec.thinking,
                "judge_model": judge_model,
                "embedding_model": embedding_model,
                "use_cache": use_cache,
            },
            repeats=repeats,
            concurrency=max(1, min(concurrency, settings.eval_max_concurrency)),
            pricing_snapshot={
                "model": resolved.label,
                "input_price_per_mtok": m.input_price_per_mtok,
                "output_price_per_mtok": m.output_price_per_mtok,
                "captured_at": datetime.now(UTC).isoformat(),
            },
            total_items=total,
            created_by=created_by,
        )
        session.add(run)
        runs.append(run)
    await session.flush()
    return runs


Sleep = Callable[[float], Awaitable[None]]


class RunExecutor:
    """Executes (or resumes) one run. Construct, then `await execute()`."""

    def __init__(
        self,
        run_id: str,
        workspace_id: str,
        *,
        cancel: asyncio.Event | None = None,
        sleep: Sleep = asyncio.sleep,
        rand: Callable[[], float] = random.random,
    ):
        self.run_id = run_id
        self.workspace_id = workspace_id
        self.cancel = cancel or asyncio.Event()
        self._sleep = sleep
        self._rand = rand
        self._judge_clients: dict[str, tuple[Any, LLMClient]] = {}

    # ── setup ───────────────────────────────────────────────

    async def _load(self):
        async with get_sessionmaker()() as session:
            run = (
                await session.execute(
                    select(EvalRun).where(
                        EvalRun.id == self.run_id,
                        EvalRun.workspace_id == self.workspace_id,
                    )
                )
            ).scalar_one()
            loaded = await load_version_by_id(
                session, self.workspace_id, run.suite_version_id
            )
            model = (
                await session.get(Model, run.model_ref_id) if run.model_ref_id else None
            )
            provider = await session.get(Provider, model.provider_id) if model else None
            done = set(
                (
                    await session.execute(
                        select(EvalResult.case_id, EvalResult.repeat_index).where(
                            EvalResult.run_id == run.id
                        )
                    )
                ).all()
            )
        return run, loaded, model, provider, done

    async def _set_status(self, status: str, **fields) -> None:
        async with get_sessionmaker()() as session:
            await session.execute(
                update(EvalRun)
                .where(EvalRun.id == self.run_id)
                .values(status=status, **fields)
            )
            await session.commit()

    # ── model calls ─────────────────────────────────────────

    async def _call(
        self, client: LLMClient, provider_id: str, model_id: str, messages, params
    ) -> ChatResult:
        """One model call with per-provider throttling and retries."""
        throttle = limiter.for_provider(provider_id)
        attempt = 0
        while True:
            try:
                async with throttle.slot():
                    return await client.chat(model_id, messages, **params)
            except LLMError as err:
                if not err.retryable or attempt >= settings.eval_max_retries:
                    raise
                # Full jitter: uniform in [0, min(cap, base * 2^attempt)].
                delay = self._rand() * min(
                    settings.eval_retry_max_s, settings.eval_retry_base_s * 2**attempt
                )
                if err.retry_after_s is not None:
                    delay = max(delay, err.retry_after_s)
                logger.info(
                    f"Eval run {self.run_id}: retrying after {err.kind} "
                    f"(attempt {attempt + 1}) in {delay:.2f}s"
                )
                await self._sleep(delay)
                attempt += 1

    async def _cached_chat(
        self, client, provider_id, model_id, messages, params, repeat, use_cache
    ) -> tuple[dict[str, Any], bool]:
        key = None
        if use_cache:
            key = cache.cache_key(
                provider_id=provider_id,
                model_id=model_id,
                params=params,
                messages=messages,
                repeat_index=repeat,
            )
            hit = await cache.get(self.workspace_id, key)
            if hit is not None:
                return hit, True
        result = await self._call(client, provider_id, model_id, messages, params)
        response = {
            "content": result.content,
            "reasoning": result.reasoning,
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "reasoning_tokens": result.usage.reasoning_tokens,
            "usage_reported": result.usage.reported,
            "latency_ms": result.latency_ms,
            "finish_reason": result.finish_reason,
        }
        if key is not None:
            await cache.put(self.workspace_id, key, response)
        return response, False

    def _context(self, variant: dict[str, Any]) -> EvalContext:
        use_cache = variant.get("use_cache", True)

        async def resolve(ref: str):
            if ref not in self._judge_clients:
                async with get_sessionmaker()() as session:
                    resolved = await resolve_model(session, self.workspace_id, ref)
                self._judge_clients[ref] = (resolved, resolved.client())
            return self._judge_clients[ref]

        async def judge(ref: str, messages, params) -> JudgeReply:
            resolved, client = await resolve(ref)
            if not resolved.model.supports_json:
                params = {k: v for k, v in params.items() if k != "response_format"}
            prefix, knobs = reasoning_controls(
                resolved.provider.preset, resolved.model.supports_reasoning, False
            )
            response, _ = await self._cached_chat(
                client,
                resolved.provider.id,
                resolved.model.model_id,
                prefix + messages,
                {**params, **knobs},
                0,
                use_cache,
            )
            return JudgeReply(
                content=response["content"],
                model_id=resolved.model.model_id,
                label=resolved.label,
            )

        async def embed(ref: str, texts: list[str]) -> list[list[float]]:
            resolved, client = await resolve(ref)
            return await client.embed(resolved.model.model_id, texts)

        return EvalContext(
            judge=judge,
            embed=embed,
            default_judge_model=variant.get("judge_model") or "default",
            default_embedding_model=variant.get("embedding_model"),
        )

    # ── execution ───────────────────────────────────────────

    async def _cancelled(self) -> bool:
        if self.cancel.is_set():
            return True
        async with get_sessionmaker()() as session:
            status = (
                await session.execute(
                    select(EvalRun.status).where(EvalRun.id == self.run_id)
                )
            ).scalar_one()
        if status == "cancelling":
            self.cancel.set()
        return self.cancel.is_set()

    async def execute(self) -> str:
        """Runs every not-yet-done item; returns the final status."""
        run, loaded, model, provider, done = await self._load()
        if model is None or provider is None:
            await self._set_status(
                "failed",
                error="The run's model no longer exists",
                finished_at=datetime.now(UTC),
            )
            return "failed"
        try:
            client = provider_service.client_for(provider)
        except Exception as exc:
            await self._set_status(
                "failed", error=str(exc), finished_at=datetime.now(UTC)
            )
            return "failed"

        await self._set_status(
            "running", started_at=run.started_at or datetime.now(UTC), error=None
        )
        variant = run.variant
        params = dict(variant.get("params") or {})
        ctx = self._context(variant)
        prices = run.pricing_snapshot
        semaphore = asyncio.Semaphore(run.concurrency)
        definitions = {c.id: c for c in loaded.definition.cases}

        todo = [
            (case, r)
            for case in loaded.cases
            for r in range(run.repeats)
            if (case.id, r) not in done
        ]

        async def worker(case: EvalCase, repeat: int) -> None:
            async with semaphore:
                if await self._cancelled():
                    return
                await self._run_item(
                    case,
                    definitions[case.case_key],
                    repeat,
                    loaded,
                    client,
                    model,
                    provider,
                    params,
                    prices,
                    ctx,
                    variant.get("use_cache", True),
                    bool(variant.get("thinking", False)),
                )

        try:
            await asyncio.gather(*(worker(c, r) for c, r in todo))
        except asyncio.CancelledError:
            await self._finalize("cancelled")
            raise
        return await self._finalize("cancelled" if self.cancel.is_set() else None)

    async def _run_item(
        self,
        case: EvalCase,
        definition: CaseDefinition,
        repeat: int,
        loaded: LoadedSuite,
        client: LLMClient,
        model: Model,
        provider: Provider,
        params: dict[str, Any],
        prices: dict[str, Any],
        ctx: EvalContext,
        use_cache: bool,
        thinking: bool = False,
    ) -> None:
        result = EvalResult(
            workspace_id=self.workspace_id,
            run_id=self.run_id,
            case_id=case.id,
            repeat_index=repeat,
        )
        try:
            messages = build_messages(loaded.definition, case.vars)
            # WHY: Same reasoning knobs as chat (e.g. Ollama models otherwise spend
            # max_tokens on hidden reasoning). Part of the request, so part of the
            # cache key too.
            prefix, knobs = reasoning_controls(
                provider.preset, model.supports_reasoning, thinking
            )
            response, was_cached = await self._cached_chat(
                client,
                provider.id,
                model.model_id,
                prefix + messages,
                {**params, **knobs},
                repeat,
                use_cache,
            )
            usage = Usage(
                input_tokens=response["input_tokens"],
                output_tokens=response["output_tokens"],
                reasoning_tokens=response.get("reasoning_tokens", 0),
                reported=response.get("usage_reported", True),
            )
            cost = compute_cost(
                usage,
                prices.get("input_price_per_mtok"),
                prices.get("output_price_per_mtok"),
            )
            result.output = response["content"]
            result.reasoning = response.get("reasoning")
            result.input_tokens = usage.input_tokens
            result.output_tokens = usage.output_tokens
            result.latency_ms = response["latency_ms"]
            result.cost_usd = cost or 0.0
            result.cached = was_cached

            assertions = effective_assertions(
                loaded.definition,
                [Assertion.model_validate(a) for a in case.assertions],
                case.expected,
            )
            score, passed, outcomes = await evaluate_case(
                assertions,
                EvalInput(
                    output=response["content"],
                    expected=case.expected,
                    vars=case.vars,
                    prompt=messages[-1]["content"],
                    latency_ms=response["latency_ms"],
                    cost_usd=cost,
                    candidate_model=model.model_id,
                ),
                ctx,
            )
            result.score = score
            result.passed = passed
            result.evaluator_results = [o.to_dict() for o in outcomes]
        except TemplateError as exc:
            result.error = str(exc)
        except LLMError as exc:
            result.error = f"{exc.kind}: {exc.message}"
        except Exception as exc:  # never let one item take the run down
            logger.exception(f"Eval run {self.run_id}: item {definition.id} failed")
            result.error = f"{type(exc).__name__}: {exc}"

        failed = result.error is not None
        async with get_sessionmaker()() as session:
            session.add(result)
            await session.execute(
                update(EvalRun)
                .where(EvalRun.id == self.run_id)
                .values(
                    completed_items=EvalRun.completed_items + 1,
                    failed_items=EvalRun.failed_items + (1 if failed else 0),
                )
            )
            await session.commit()

    async def _finalize(self, forced_status: str | None) -> str:
        async with get_sessionmaker()() as session:
            row = (
                await session.execute(
                    select(
                        func.count(),
                        func.avg(EvalResult.score),
                        func.coalesce(func.sum(EvalResult.cost_usd), 0.0),
                        func.coalesce(
                            func.sum(
                                EvalResult.input_tokens + EvalResult.output_tokens
                            ),
                            0,
                        ),
                    ).where(EvalResult.run_id == self.run_id)
                )
            ).one()
            passed_count = (
                await session.execute(
                    select(func.count()).where(
                        EvalResult.run_id == self.run_id, EvalResult.passed.is_(True)
                    )
                )
            ).scalar_one()
            errors = (
                await session.execute(
                    select(func.count()).where(
                        EvalResult.run_id == self.run_id, EvalResult.error.isnot(None)
                    )
                )
            ).scalar_one()
            total = int(row[0])
            run = await session.get(EvalRun, self.run_id)
            if forced_status:
                status = forced_status
            elif total and errors == total:
                status = "failed"
                run.error = "Every item failed; see the results for details"
            else:
                status = "completed"
            run.status = status
            run.mean_score = float(row[1]) if total else None
            run.pass_rate = passed_count / total if total else None
            run.total_cost_usd = float(row[2])
            run.total_tokens = int(row[3])
            run.finished_at = datetime.now(UTC)
            await session.commit()
        logger.info(f"Eval run {self.run_id} finished: {status}")
        return status


# ── Background execution registry ───────────────────────────


@dataclass
class _Active:
    task: asyncio.Task
    cancel: asyncio.Event


_active: dict[str, _Active] = {}


def start(run_id: str, workspace_id: str, **executor_kwargs) -> asyncio.Task:
    """Runs the executor in the background (in this process)."""
    cancel = asyncio.Event()
    executor = RunExecutor(run_id, workspace_id, cancel=cancel, **executor_kwargs)

    async def _go():
        try:
            return await executor.execute()
        except Exception:
            logger.exception(f"Eval run {run_id} crashed")
            await executor._set_status(
                "failed", error="Internal error", finished_at=datetime.now(UTC)
            )
            return "failed"
        finally:
            _active.pop(run_id, None)

    task = asyncio.create_task(_go())
    _active[run_id] = _Active(task, cancel)
    return task


async def wait(run_id: str) -> None:
    active = _active.get(run_id)
    if active is not None:
        await asyncio.shield(active.task)


async def request_cancel(session, workspace_id: str, run_id: str) -> str:
    run = (
        await session.execute(
            select(EvalRun).where(
                EvalRun.id == run_id, EvalRun.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()
    if run is None:
        raise ValidationException("Run not found")
    if run.status not in ACTIVE_STATUSES:
        return run.status
    if run_id in _active:
        _active[run_id].cancel.set()
        run.status = "cancelling"
    else:
        # Not executing in this process (or never started): just mark it.
        run.status = "cancelled"
        run.finished_at = datetime.now(UTC)
    await session.commit()
    return run.status


async def prepare_resume(
    session, workspace_id: str, run_id: str, retry_errors: bool
) -> EvalRun:
    run = (
        await session.execute(
            select(EvalRun).where(
                EvalRun.id == run_id, EvalRun.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()
    if run is None:
        raise ValidationException("Run not found")
    if run.status in ACTIVE_STATUSES or run_id in _active:
        raise ValidationException("The run is already running")
    if retry_errors:
        removed = await session.execute(
            delete(EvalResult).where(
                EvalResult.run_id == run_id, EvalResult.error.isnot(None)
            )
        )
        run.completed_items -= removed.rowcount or 0
        run.failed_items = 0
    run.status = "pending"
    run.finished_at = None
    await session.commit()
    return run


async def mark_interrupted_runs() -> int:
    """At startup: runs left active by a crash/restart can be resumed."""
    async with get_sessionmaker()() as session:
        result = await session.execute(
            update(EvalRun)
            .where(EvalRun.status.in_((*ACTIVE_STATUSES, "cancelling")))
            .values(status="interrupted", error="Server restarted during the run")
        )
        await session.commit()
        return result.rowcount or 0
