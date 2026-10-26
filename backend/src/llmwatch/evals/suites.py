"""
Module: suites.py
Purpose: Stores eval suites as immutable versions.
WHY: A run must always be reproducible against exactly the prompt and cases it used.
Editing a suite therefore never changes an existing version: it creates a new one
(unless nothing changed), and runs pin the version they executed.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.db.models import EvalCase, EvalSuite, EvalSuiteVersion
from llmwatch.db.repository import WorkspaceRepository
from llmwatch.evals.schema import Assertion, CaseDefinition, SuiteDefinition
from llmwatch.exceptions import ConflictException, ResourceNotFoundException


class SuiteRepository(WorkspaceRepository[EvalSuite]):
    model = EvalSuite

    async def by_name(self, name: str) -> EvalSuite | None:
        stmt = self.select().where(EvalSuite.name == name)
        return (await self.session.execute(stmt)).scalar_one_or_none()


@dataclass
class LoadedSuite:
    suite: EvalSuite
    version: EvalSuiteVersion
    cases: list[EvalCase]
    definition: SuiteDefinition


def _assertions(raw: list[dict]) -> list[Assertion]:
    return [Assertion.model_validate(a) for a in raw]


def _assertion_rows(items: list[Assertion]) -> list[dict]:
    return [a.model_dump(mode="json", exclude_none=False) for a in items]


async def _write_version(
    session: AsyncSession, suite: EvalSuite, number: int, definition: SuiteDefinition
) -> EvalSuiteVersion:
    version = EvalSuiteVersion(
        workspace_id=suite.workspace_id,
        suite_id=suite.id,
        version=number,
        prompt_template=definition.prompt,
        system_prompt=definition.system_prompt,
        default_assertions=_assertion_rows(definition.default_assertions),
    )
    session.add(version)
    await session.flush()
    for position, case in enumerate(definition.cases):
        session.add(
            EvalCase(
                workspace_id=suite.workspace_id,
                suite_version_id=version.id,
                position=position,
                case_key=case.id,
                vars=case.vars,
                expected=case.expected,
                assertions=_assertion_rows(case.assertions),
                tags=case.tags,
            )
        )
    await session.flush()
    return version


async def create_suite(
    session: AsyncSession, workspace_id: str, definition: SuiteDefinition
) -> EvalSuite:
    repo = SuiteRepository(session, workspace_id)
    if await repo.by_name(definition.name):
        raise ConflictException(f"A suite named {definition.name!r} already exists")
    suite = repo.add(
        EvalSuite(
            name=definition.name,
            description=definition.description,
            latest_version=1,
        )
    )
    await session.flush()
    await _write_version(session, suite, 1, definition)
    return suite


async def save_new_version(
    session: AsyncSession, suite: EvalSuite, definition: SuiteDefinition
) -> tuple[EvalSuiteVersion, bool]:
    """Stores `definition` as the next version unless it matches the latest one.

    Returns (version, created). Name and description changes don't need a version.
    """
    if definition.name != suite.name:
        clash = await SuiteRepository(session, suite.workspace_id).by_name(
            definition.name
        )
        if clash is not None and clash.id != suite.id:
            raise ConflictException(f"A suite named {definition.name!r} already exists")
    suite.name = definition.name
    suite.description = definition.description
    suite.updated_at = datetime.now(UTC)

    latest = await load_suite(session, suite.workspace_id, suite.id)
    if latest.definition.content_hash_input() == definition.content_hash_input():
        await session.flush()
        return latest.version, False

    suite.latest_version += 1
    version = await _write_version(session, suite, suite.latest_version, definition)
    return version, True


async def load_suite(
    session: AsyncSession,
    workspace_id: str,
    suite_id: str,
    version: int | None = None,
) -> LoadedSuite:
    suite = await SuiteRepository(session, workspace_id).get(suite_id)
    if suite is None:
        raise ResourceNotFoundException("Suite not found")
    number = version or suite.latest_version
    row = (
        await session.execute(
            select(EvalSuiteVersion).where(
                EvalSuiteVersion.suite_id == suite.id,
                EvalSuiteVersion.version == number,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFoundException(f"Suite version {number} not found")
    return await _loaded(session, suite, row)


async def load_version_by_id(
    session: AsyncSession, workspace_id: str, version_id: str
) -> LoadedSuite:
    row = (
        await session.execute(
            select(EvalSuiteVersion).where(
                EvalSuiteVersion.id == version_id,
                EvalSuiteVersion.workspace_id == workspace_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFoundException("Suite version not found")
    suite = await SuiteRepository(session, workspace_id).get(row.suite_id)
    return await _loaded(session, suite, row)


async def _loaded(
    session: AsyncSession, suite: EvalSuite, row: EvalSuiteVersion
) -> LoadedSuite:
    cases = list(
        (
            await session.execute(
                select(EvalCase)
                .where(EvalCase.suite_version_id == row.id)
                .order_by(EvalCase.position)
            )
        ).scalars()
    )
    definition = SuiteDefinition(
        name=suite.name,
        description=suite.description,
        prompt=row.prompt_template,
        system_prompt=row.system_prompt,
        default_assertions=_assertions(row.default_assertions),
        cases=[
            CaseDefinition(
                id=c.case_key,
                vars=c.vars,
                expected=c.expected,
                assertions=_assertions(c.assertions),
                tags=c.tags,
            )
            for c in cases
        ],
    )
    return LoadedSuite(suite, row, cases, definition)


async def list_versions(session: AsyncSession, suite: EvalSuite) -> list[dict]:
    rows = (
        await session.execute(
            select(
                EvalSuiteVersion.version,
                EvalSuiteVersion.id,
                EvalSuiteVersion.created_at,
                func.count(EvalCase.id),
            )
            .join(
                EvalCase, EvalCase.suite_version_id == EvalSuiteVersion.id, isouter=True
            )
            .where(EvalSuiteVersion.suite_id == suite.id)
            .group_by(EvalSuiteVersion.id)
            .order_by(EvalSuiteVersion.version.desc())
        )
    ).all()
    return [
        {"version": v, "id": vid, "created_at": created, "case_count": n}
        for v, vid, created, n in rows
    ]


async def case_counts(session: AsyncSession, workspace_id: str) -> dict[str, int]:
    """Cases in the latest version of every suite, keyed by suite id."""
    rows = (
        await session.execute(
            select(EvalSuite.id, func.count(EvalCase.id))
            .join(
                EvalSuiteVersion,
                (EvalSuiteVersion.suite_id == EvalSuite.id)
                & (EvalSuiteVersion.version == EvalSuite.latest_version),
            )
            .join(
                EvalCase, EvalCase.suite_version_id == EvalSuiteVersion.id, isouter=True
            )
            .where(EvalSuite.workspace_id == workspace_id)
            .group_by(EvalSuite.id)
        )
    ).all()
    return {suite_id: n for suite_id, n in rows}
