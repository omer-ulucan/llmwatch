"""
Module: evals.py (router)
Purpose: Eval suites: create, version, import/export and preview.
WHY: Suites are edited in the UI, imported from YAML/JSON files and pushed by the CLI
(with an API key), so these endpoints accept any authenticated workspace member.
"""

from typing import Any, Dict, Literal

from fastapi import APIRouter, Body, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.auth.dependencies import get_current_user
from llmwatch.db.engine import get_session
from llmwatch.db.models import EvalSuite
from llmwatch.evals import suites as suite_service
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
