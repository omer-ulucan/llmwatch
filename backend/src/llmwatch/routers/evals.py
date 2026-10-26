"""
Module: evals.py (router)
Purpose: Eval suites: create, version, import/export and preview.
WHY: Suites are edited in the UI, imported from YAML/JSON files and pushed by the CLI
(with an API key), so these endpoints accept any authenticated workspace member.
"""

from typing import Any, Dict, Literal

from fastapi import APIRouter, Body, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.auth.dependencies import get_current_user
from llmwatch.db.engine import get_session
from llmwatch.db.models import EvalCase, EvalResult, EvalRun, EvalSuite
from llmwatch.evals import runner
from llmwatch.evals import suites as suite_service
from llmwatch.evals.compare import compare_runs
from llmwatch.evals.messages import build_messages
from llmwatch.evals.schema import (
    SuiteDefinition,
    SuiteFormatError,
    dump_suite,
    parse_suite,
)
from llmwatch.evals.template import TemplateError
from llmwatch.exceptions import ResourceNotFoundException, ValidationException
from llmwatch.rate_limit import limiter

router = APIRouter(prefix="/evals", tags=["Evals"])

Format = Literal["yaml", "json"]


def _suite_out(suite: EvalSuite, case_count: int | None = None) -> dict[str, Any]:
    return {
        "id": suite.id,
        "name": suite.name,
        "description": suite.description,
        "latest_version": suite.latest_version,
        "baseline_run_id": suite.baseline_run_id,
        "case_count": case_count,
        "created_at": suite.created_at,
        "updated_at": suite.updated_at,
    }


async def _detail(session: AsyncSession, loaded: suite_service.LoadedSuite) -> dict:
    return {
        **_suite_out(loaded.suite, len(loaded.cases)),
        "version": loaded.version.version,
        "version_id": loaded.version.id,
        "definition": loaded.definition.to_document(),
        "versions": await suite_service.list_versions(session, loaded.suite),
    }


@router.get("/suites")
async def list_suites(
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    repo = suite_service.SuiteRepository(session, current_user["workspace_id"])
    counts = await suite_service.case_counts(session, current_user["workspace_id"])
    suites = await repo.list(order_by=EvalSuite.updated_at.desc())
    return {"suites": [_suite_out(s, counts.get(s.id, 0)) for s in suites]}


@router.post("/suites", status_code=201)
@limiter.limit("60/minute")
async def create_suite(
    request: Request,
    definition: SuiteDefinition,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    suite = await suite_service.create_suite(
        session, current_user["workspace_id"], definition
    )
    await session.commit()
    return await _detail(
        session,
        await suite_service.load_suite(session, current_user["workspace_id"], suite.id),
    )


class ImportBody(BaseModel):
    content: str = Field(..., min_length=1, max_length=5_000_000)
    format: Format = "yaml"


@router.post("/suites/import")
@limiter.limit("30/minute")
async def import_suite(
    request: Request,
    body: ImportBody,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Imports a YAML/JSON suite. A suite with the same name gets a new version
    (or none, if nothing changed); otherwise a new suite is created.
    """
    try:
        definition = parse_suite(body.content, body.format)
    except SuiteFormatError as exc:
        raise ValidationException(str(exc)) from exc
    workspace_id = current_user["workspace_id"]
    existing = await suite_service.SuiteRepository(session, workspace_id).by_name(
        definition.name
    )
    if existing is None:
        suite = await suite_service.create_suite(session, workspace_id, definition)
        created_suite, created_version = True, True
    else:
        suite = existing
        _, created_version = await suite_service.save_new_version(
            session, suite, definition
        )
        created_suite = False
    await session.commit()
    detail = await _detail(
        session, await suite_service.load_suite(session, workspace_id, suite.id)
    )
    return {
        **detail,
        "created_suite": created_suite,
        "created_version": created_version,
    }


@router.get("/suites/{suite_id}")
async def get_suite(
    suite_id: str,
    version: int | None = Query(None, ge=1),
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    loaded = await suite_service.load_suite(
        session, current_user["workspace_id"], suite_id, version
    )
    return await _detail(session, loaded)


@router.put("/suites/{suite_id}")
@limiter.limit("60/minute")
async def update_suite(
    request: Request,
    suite_id: str,
    definition: SuiteDefinition,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Saves a new version (only if the prompt, assertions or cases changed)."""
    workspace_id = current_user["workspace_id"]
    suite = await suite_service.SuiteRepository(session, workspace_id).get(suite_id)
    if suite is None:
        raise ResourceNotFoundException("Suite not found")
    _, created = await suite_service.save_new_version(session, suite, definition)
    await session.commit()
    detail = await _detail(
        session, await suite_service.load_suite(session, workspace_id, suite_id)
    )
    return {**detail, "created_version": created}


@router.delete("/suites/{suite_id}", status_code=204)
async def delete_suite(
    suite_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    repo = suite_service.SuiteRepository(session, current_user["workspace_id"])
    suite = await repo.get(suite_id)
    if suite is None:
        raise ResourceNotFoundException("Suite not found")
    # Runs and results cascade with the suite.
    await repo.delete(suite)
    await session.commit()
    return Response(status_code=204)


@router.get("/suites/{suite_id}/export")
async def export_suite(
    suite_id: str,
    format: Format = "yaml",
    version: int | None = Query(None, ge=1),
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    loaded = await suite_service.load_suite(
        session, current_user["workspace_id"], suite_id, version
    )
    text = dump_suite(loaded.definition, format)
    filename = f"{loaded.suite.name}.v{loaded.version.version}.{format}"
    return Response(
        content=text,
        media_type="application/yaml" if format == "yaml" else "application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class PreviewBody(BaseModel):
    case_id: str | None = None
    vars: dict[str, Any] | None = None
    version: int | None = Field(None, ge=1)


@router.post("/suites/{suite_id}/preview")
async def preview(
    suite_id: str,
    body: PreviewBody = Body(default_factory=PreviewBody),
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """The exact messages a case would send (first case unless one is given)."""
    loaded = await suite_service.load_suite(
        session, current_user["workspace_id"], suite_id, body.version
    )
    case = None
    if body.vars is None:
        cases = loaded.definition.cases
        case = (
            next((c for c in cases if c.id == body.case_id), None)
            if body.case_id
            else cases[0]
        )
        if case is None:
            raise ResourceNotFoundException(f"Case {body.case_id!r} not found")
    values = body.vars if body.vars is not None else case.vars
    try:
        messages = build_messages(loaded.definition, values)
    except TemplateError as exc:
        raise ValidationException(str(exc)) from exc
    return {"case_id": case.id if case else None, "messages": messages}


# ── Runs ────────────────────────────────────────────────────


class VariantBody(BaseModel):
    model: str = Field(..., min_length=1, max_length=300)
    label: str = Field("", max_length=200)
    temperature: float | None = Field(None, ge=0, le=2)
    max_tokens: int | None = Field(None, gt=0, le=200_000)
    top_p: float | None = Field(None, gt=0, le=1)
    seed: int | None = None


class RunBody(BaseModel):
    suite_id: str
    version: int | None = Field(None, ge=1)
    variants: list[VariantBody] = Field(..., min_length=1, max_length=10)
    repeats: int = Field(1, ge=1, le=20)
    concurrency: int = Field(4, ge=1, le=64)
    judge_model: str | None = None
    embedding_model: str | None = None
    use_cache: bool = True


def run_out(run) -> dict[str, Any]:
    return {
        "id": run.id,
        "suite_id": run.suite_id,
        "suite_version_id": run.suite_version_id,
        "group_id": run.group_id,
        "label": run.label,
        "status": run.status,
        "variant": run.variant,
        "repeats": run.repeats,
        "concurrency": run.concurrency,
        "pricing_snapshot": run.pricing_snapshot,
        "total_items": run.total_items,
        "completed_items": run.completed_items,
        "failed_items": run.failed_items,
        "mean_score": run.mean_score,
        "pass_rate": run.pass_rate,
        "total_cost_usd": run.total_cost_usd,
        "total_tokens": run.total_tokens,
        "error": run.error,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


async def _get_run(session: AsyncSession, workspace_id: str, run_id: str):
    run = (
        await session.execute(
            select(EvalRun).where(
                EvalRun.id == run_id, EvalRun.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()
    if run is None:
        raise ResourceNotFoundException("Run not found")
    return run


@router.post("/runs", status_code=202)
@limiter.limit("30/minute")
async def create_runs(
    request: Request,
    body: RunBody,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Starts one run per variant (model + params) in the background. Poll
    GET /evals/runs/{id} for progress.
    """
    runs = await runner.create_runs(
        session,
        current_user["workspace_id"],
        suite_id=body.suite_id,
        version=body.version,
        variants=[
            runner.VariantSpec(
                model=v.model,
                label=v.label,
                params={
                    "temperature": v.temperature,
                    "max_tokens": v.max_tokens,
                    "top_p": v.top_p,
                    "seed": v.seed,
                },
            )
            for v in body.variants
        ],
        repeats=body.repeats,
        concurrency=body.concurrency,
        judge_model=body.judge_model,
        embedding_model=body.embedding_model,
        use_cache=body.use_cache,
        created_by=current_user["user_id"],
    )
    await session.commit()
    for run in runs:
        runner.start(run.id, current_user["workspace_id"])
    return {"runs": [run_out(r) for r in runs]}


@router.get("/runs")
async def list_runs(
    suite_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(EvalRun).where(EvalRun.workspace_id == current_user["workspace_id"])
    if suite_id:
        stmt = stmt.where(EvalRun.suite_id == suite_id)
    stmt = stmt.order_by(EvalRun.created_at.desc()).limit(limit)
    runs = (await session.execute(stmt)).scalars().all()
    return {"runs": [run_out(r) for r in runs]}


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return run_out(await _get_run(session, current_user["workspace_id"], run_id))


@router.get("/runs/{run_id}/results")
async def get_run_results(
    run_id: str,
    status: Literal["passed", "failed", "error"] | None = None,
    tag: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Per-case results with the case inputs and evaluator reasons."""
    run = await _get_run(session, current_user["workspace_id"], run_id)
    conds = [EvalResult.run_id == run.id]
    if status == "passed":
        conds.append(EvalResult.passed.is_(True))
    elif status == "failed":
        conds.append(EvalResult.passed.is_(False))
    elif status == "error":
        conds.append(EvalResult.error.isnot(None))
    stmt = (
        select(EvalResult, EvalCase)
        .join(EvalCase, EvalCase.id == EvalResult.case_id)
        .where(*conds)
        .order_by(EvalCase.position, EvalResult.repeat_index)
    )
    rows = (await session.execute(stmt)).all()
    if tag:
        rows = [(r, c) for r, c in rows if tag in (c.tags or [])]
    total = len(rows)
    rows = rows[(page - 1) * page_size : page * page_size]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": r.id,
                "case_id": c.case_key,
                "repeat_index": r.repeat_index,
                "vars": c.vars,
                "expected": c.expected,
                "tags": c.tags,
                "output": r.output,
                "reasoning": r.reasoning,
                "score": r.score,
                "passed": r.passed,
                "error": r.error,
                "cached": r.cached,
                "latency_ms": r.latency_ms,
                "cost_usd": r.cost_usd,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "evaluator_results": r.evaluator_results,
            }
            for r, c in rows
        ],
    }


@router.post("/runs/{run_id}/cancel", status_code=202)
async def cancel_run(
    run_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _get_run(session, current_user["workspace_id"], run_id)
    status = await runner.request_cancel(session, current_user["workspace_id"], run_id)
    return {"id": run_id, "status": status}


@router.post("/runs/{run_id}/resume", status_code=202)
async def resume_run(
    run_id: str,
    retry_errors: bool = False,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Continues a cancelled, interrupted or failed run from where it stopped
    (optionally re-trying items that errored)."""
    await _get_run(session, current_user["workspace_id"], run_id)
    run = await runner.prepare_resume(
        session, current_user["workspace_id"], run_id, retry_errors
    )
    runner.start(run.id, current_user["workspace_id"])
    return run_out(run)


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(
    run_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    run = await _get_run(session, current_user["workspace_id"], run_id)
    if run.status in runner.ACTIVE_STATUSES:
        raise ValidationException("Cancel the run before deleting it")
    await session.delete(run)
    await session.commit()
    return Response(status_code=204)


# ── Comparison and baselines ────────────────────────────────


@router.get("/compare")
async def compare(
    candidate: str,
    baseline: str | None = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Compares a candidate run with a baseline run of the same suite (the suite's
    marked baseline if `baseline` is omitted): paired bootstrap CI for the score
    delta, McNemar test for pass/fail, cost and latency deltas, per-case changes.
    """
    workspace_id = current_user["workspace_id"]
    if baseline is None:
        cand = await _get_run(session, workspace_id, candidate)
        suite = await session.get(EvalSuite, cand.suite_id)
        if suite is None or suite.baseline_run_id is None:
            raise ValidationException(
                "No baseline given and the suite has no baseline run marked"
            )
        baseline = suite.baseline_run_id
    return await compare_runs(session, workspace_id, baseline, candidate)


class BaselineBody(BaseModel):
    run_id: str | None = None


@router.put("/suites/{suite_id}/baseline")
async def set_baseline(
    suite_id: str,
    body: BaselineBody,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Marks a run as the suite's baseline (or clears it with run_id null)."""
    workspace_id = current_user["workspace_id"]
    suite = await suite_service.SuiteRepository(session, workspace_id).get(suite_id)
    if suite is None:
        raise ResourceNotFoundException("Suite not found")
    if body.run_id is not None:
        run = await _get_run(session, workspace_id, body.run_id)
        if run.suite_id != suite.id:
            raise ValidationException("That run belongs to another suite")
        if run.status != "completed":
            raise ValidationException("Only completed runs can be the baseline")
    suite.baseline_run_id = body.run_id
    await session.commit()
    return _suite_out(suite)
