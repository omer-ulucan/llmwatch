"""
Tests for `llmwatch eval run` / `llmwatch eval compare`: local mode (same database)
and server mode (API key over HTTP, here an in-process transport), and the exit codes
CI relies on.
"""

import io
import json

import httpx
import pytest

from llmwatch.cli import build_parser
from llmwatch.evals import cli as eval_cli
from llmwatch.evals.cli import EXIT_ERROR, EXIT_OK, EXIT_REGRESSION, run_eval_command

CASES = 12
SUITE = "name: ci-suite\nprompt: 'Say {{ word }}'\ncases:\n" + "".join(
    f"  - {{id: c{i:02d}, vars: {{word: w{i}}}, expected: w{i}}}\n"
    for i in range(CASES)
)


@pytest.fixture
def suite_file(tmp_path):
    path = tmp_path / "suite.yaml"
    path.write_text(SUITE)
    return path


@pytest.fixture
async def workspace(make_account, add_model):
    acct = await make_account(workspace="CI")
    await add_model(acct)
    return acct


async def cli(*argv: str) -> tuple[int, str, str]:
    args = build_parser().parse_args(list(argv))
    out, err = io.StringIO(), io.StringIO()
    code = await run_eval_command(args, out, err)
    return code, out.getvalue(), err.getvalue()


def answer_all(fake, correct: bool):
    for i in range(CASES):
        fake.reply(f"w{i}" if correct else "wrong")


# ── Local mode ──────────────────────────────────────────────


async def test_local_run_prints_a_summary(workspace, fake_llm, suite_file):
    answer_all(fake_llm, correct=True)
    code, out, err = await cli(
        "eval", "run", str(suite_file), "--model", "fake-model", "--concurrency", "1"
    )

    assert code == EXIT_OK, err
    assert "Suite ci-suite v1" in out
    assert "completed" in out
    assert "pass 100.0%" in out


async def test_regression_fails_the_build(workspace, fake_llm, suite_file):
    answer_all(fake_llm, correct=True)
    code, _, _ = await cli(
        "eval",
        "run",
        str(suite_file),
        "--model",
        "fake-model",
        "--concurrency",
        "1",
        "--set-baseline",
    )
    assert code == EXIT_OK

    answer_all(fake_llm, correct=False)
    code, out, err = await cli(
        "eval",
        "run",
        str(suite_file),
        "--model",
        "fake-model",
        "--concurrency",
        "1",
        "--no-cache",
        "--baseline",
        "suite",
        "--fail-on-regression",
    )

    assert code == EXIT_REGRESSION
    assert "REGRESSED" in out
    assert "significant" in out
    assert "Significant regression detected" in err


async def test_regression_without_the_flag_still_exits_zero(
    workspace, fake_llm, suite_file
):
    answer_all(fake_llm, correct=True)
    await cli("eval", "run", str(suite_file), "--model", "fake-model", "--set-baseline")
    answer_all(fake_llm, correct=False)
    code, out, _ = await cli(
        "eval",
        "run",
        str(suite_file),
        "--model",
        "fake-model",
        "--no-cache",
        "--baseline",
        "suite",
    )
    assert code == EXIT_OK
    assert "REGRESSED" in out


async def test_noise_does_not_fail_the_build(workspace, fake_llm, suite_file):
    answer_all(fake_llm, correct=True)
    await cli(
        "eval",
        "run",
        str(suite_file),
        "--model",
        "fake-model",
        "--concurrency",
        "1",
        "--set-baseline",
    )
    # One case flips: not a significant change.
    for i in range(CASES):
        fake_llm.reply("wrong" if i == 0 else f"w{i}")
    code, out, _ = await cli(
        "eval",
        "run",
        str(suite_file),
        "--model",
        "fake-model",
        "--concurrency",
        "1",
        "--no-cache",
        "--baseline",
        "suite",
        "--fail-on-regression",
    )
    assert code == EXIT_OK
    assert "no significant difference" in out


async def test_set_baseline_is_skipped_on_regression(
    workspace, fake_llm, suite_file, db_session
):
    from sqlalchemy import select

    from llmwatch.db.models import EvalSuite

    answer_all(fake_llm, correct=True)
    await cli("eval", "run", str(suite_file), "--model", "fake-model", "--set-baseline")
    first = (await db_session.execute(select(EvalSuite))).scalar_one().baseline_run_id

    answer_all(fake_llm, correct=False)
    await cli(
        "eval",
        "run",
        str(suite_file),
        "--model",
        "fake-model",
        "--no-cache",
        "--baseline",
        "suite",
        "--set-baseline",
    )
    db_session.expire_all()
    assert (
        await db_session.execute(select(EvalSuite))
    ).scalar_one().baseline_run_id == first


async def test_json_output(workspace, fake_llm, suite_file):
    answer_all(fake_llm, correct=True)
    code, out, _ = await cli(
        "eval", "run", str(suite_file), "--model", "fake-model", "--json"
    )
    data = json.loads(out)
    assert data["exit_code"] == code == EXIT_OK
    assert data["runs"][0]["status"] == "completed"
    assert data["suite"]["name"] == "ci-suite"


async def test_params_are_passed_to_the_model(workspace, fake_llm, suite_file):
    await cli(
        "eval",
        "run",
        str(suite_file),
        "--model",
        "fake-model",
        "--param",
        "temperature=0",
        "--param",
        "max_tokens=16",
    )
    assert {r["temperature"] for r in fake_llm.requests} == {0}
    assert {r["max_tokens"] for r in fake_llm.requests} == {16}


async def test_compare_command(workspace, fake_llm, suite_file):
    answer_all(fake_llm, correct=True)
    _, out1, _ = await cli(
        "eval", "run", str(suite_file), "--model", "fake-model", "--json"
    )
    answer_all(fake_llm, correct=False)
    _, out2, _ = await cli(
        "eval", "run", str(suite_file), "--model", "fake-model", "--json", "--no-cache"
    )
    base, cand = json.loads(out1)["runs"][0]["id"], json.loads(out2)["runs"][0]["id"]

    code, out, _ = await cli("eval", "compare", base, cand, "--fail-on-regression")
    assert code == EXIT_REGRESSION
    assert "REGRESSED" in out


# ── Errors (exit 2) ─────────────────────────────────────────


async def test_missing_suite_file(workspace):
    code, _, err = await cli("eval", "run", "nope.yaml", "--model", "fake-model")
    assert code == EXIT_ERROR
    assert "not found" in err


async def test_invalid_suite_file(workspace, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "name: x\nprompt: '{{ a }}'\ncases:\n  - vars: {}\n    expected: y\n"
    )
    code, _, err = await cli("eval", "run", str(bad), "--model", "fake-model")
    assert code == EXIT_ERROR
    assert "missing vars" in err


async def test_unknown_model(workspace, suite_file):
    code, _, err = await cli("eval", "run", str(suite_file), "--model", "no-such-model")
    assert code == EXIT_ERROR
    assert "Unknown or disabled model" in err


async def test_failed_run_is_an_error(workspace, fake_llm, suite_file):
    for _ in range(CASES):
        fake_llm.fail(401, message="bad key")
    code, _, err = await cli("eval", "run", str(suite_file), "--model", "fake-model")
    assert code == EXIT_ERROR
    assert "did not complete" in err


async def test_bad_param(workspace, suite_file):
    code, _, err = await cli(
        "eval",
        "run",
        str(suite_file),
        "--model",
        "fake-model",
        "--param",
        "stream=true",
    )
    assert code == EXIT_ERROR
    assert "--param" in err


async def test_several_workspaces_need_a_choice(
    workspace, make_account, fake_llm, suite_file
):
    await make_account(workspace="Other")
    code, _, err = await cli("eval", "run", str(suite_file), "--model", "fake-model")
    assert code == EXIT_ERROR
    assert "--workspace" in err
    code, _, _ = await cli(
        "eval", "run", str(suite_file), "--model", "fake-model", "--workspace", "CI"
    )
    assert code == EXIT_OK


# ── Server mode ─────────────────────────────────────────────


@pytest.fixture
async def server(workspace, client, monkeypatch):
    """Points the CLI's HTTP client at the in-process app with a real API key."""
    from llmwatch.main import app

    key = (
        await client.post("/api-keys", json={"name": "ci"}, headers=workspace.headers)
    ).json()["raw_key"]

    def make(server_url, api_key):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": api_key},
        )

    monkeypatch.setattr(eval_cli, "make_http_client", make)
    return key


async def test_server_mode_runs_and_detects_regressions(server, fake_llm, suite_file):
    common = ["--server", "http://test", "--api-key", server, "--poll-interval", "0.01"]
    answer_all(fake_llm, correct=True)
    code, out, err = await cli(
        "eval",
        "run",
        str(suite_file),
        "--model",
        "fake-model",
        "--concurrency",
        "1",
        "--set-baseline",
        *common,
    )
    assert code == EXIT_OK, err
    assert "Marked run" in out

    answer_all(fake_llm, correct=False)
    code, out, _ = await cli(
        "eval",
        "run",
        str(suite_file),
        "--model",
        "fake-model",
        "--concurrency",
        "1",
        "--no-cache",
        "--baseline",
        "suite",
        "--fail-on-regression",
        *common,
    )
    assert code == EXIT_REGRESSION
    assert "REGRESSED" in out


async def test_server_mode_bad_api_key(server, suite_file):
    code, _, err = await cli(
        "eval",
        "run",
        str(suite_file),
        "--model",
        "fake-model",
        "--server",
        "http://test",
        "--api-key",
        "lw_wrong",
        "--poll-interval",
        "0.01",
    )
    assert code == EXIT_ERROR
    assert "401" in err


async def test_server_mode_needs_an_api_key(suite_file, monkeypatch):
    monkeypatch.delenv("LLMWATCH_API_KEY", raising=False)
    code, _, err = await cli(
        "eval", "run", str(suite_file), "--model", "m", "--server", "http://x"
    )
    assert code == EXIT_ERROR
    assert "--api-key" in err


def test_parser_wires_the_eval_commands():
    args = build_parser().parse_args(
        ["eval", "run", "s.yaml", "--model", "a", "--model", "b"]
    )
    assert args.model == ["a", "b"]
    assert args.eval_func is eval_cli.eval_run
