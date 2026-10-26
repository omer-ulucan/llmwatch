"""
The bundled example suite: valid, identical to the copy in examples/, and seeded into
the demo workspace.
"""

from pathlib import Path

from sqlalchemy import select

from llmwatch.db.models import EvalSuite
from llmwatch.evals.schema import parse_suite
from llmwatch.services import accounts

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGED = accounts.EXAMPLE_SUITE
PUBLIC = REPO_ROOT / "examples" / "support-triage.yaml"


def test_example_suite_is_valid_and_realistic():
    suite = parse_suite(PACKAGED.read_text())
    assert suite.name == "support-triage"
    assert len(suite.cases) == 20
    types = {a.type for c in suite.cases for a in c.assertions} | {
        a.type for a in suite.default_assertions
    }
    assert {
        "json_schema",
        "regex",
        "llm_judge",
        "not_contains",
        "latency_under",
    } <= types
    assert len({c.id for c in suite.cases}) == 20


def test_examples_copy_matches_the_packaged_suite():
    """examples/ is what users read; the package copy is what the server seeds."""
    assert PUBLIC.read_text() == PACKAGED.read_text()


async def test_demo_account_gets_the_example_suite(db_session):
    await accounts.ensure_demo_account(db_session)
    await accounts.ensure_demo_account(db_session)  # idempotent
    suites = (await db_session.execute(select(EvalSuite))).scalars().all()
    assert [s.name for s in suites] == ["support-triage"]
