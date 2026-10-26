"""
Module: cli.py (evals)
Purpose: `llmwatch eval run` / `llmwatch eval compare` for local use and CI.
WHY: Evals belong in CI: run a suite against a model, compare with the suite's
baseline, and fail the build only on a *significant* regression (noise doesn't
break builds). Works either locally against the same database as the server, or
against a running server with an API key.

Exit codes:
  0  finished (and, with --fail-on-regression, no significant regression)
  1  significant regression (with --fail-on-regression)
  2  usage, configuration or run error (bad suite file, unknown model, failed run)
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Protocol

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_ERROR = 2


class CLIError(Exception):
    """A problem the user must fix; printed without a traceback."""


class Backend(Protocol):
    async def import_suite(self, text: str, fmt: str) -> dict[str, Any]: ...
    async def start_runs(self, body: dict[str, Any]) -> list[dict[str, Any]]: ...
    async def wait_run(self, run_id: str) -> dict[str, Any]: ...
    async def compare(self, baseline: str, candidate: str) -> dict[str, Any]: ...
    async def set_baseline(self, suite_id: str, run_id: str) -> None: ...
    async def close(self) -> None: ...


# ── Local backend ───────────────────────────────────────────


class LocalBackend:
    """Talks to the database directly (same DATABASE_URL and SECRET_KEY as the
    server, so provider keys can be decrypted)."""

    def __init__(self, workspace_id: str, owns_engine: bool = True):
        self.workspace_id = workspace_id
        self._owns_engine = owns_engine

    @classmethod
    async def connect(cls, workspace: str | None) -> "LocalBackend":
        from sqlalchemy import or_, select

        import llmwatch.db.engine as engine_module
        from llmwatch.config import settings
        from llmwatch.db import migrate
        from llmwatch.db.engine import get_sessionmaker, is_memory_sqlite
        from llmwatch.db.models import Workspace

        # Only dispose the engine on close if this command created it.
        owns_engine = engine_module._engine is None
        if not is_memory_sqlite(settings.database_url):
            await asyncio.to_thread(migrate.upgrade, settings.database_url)
        async with get_sessionmaker()() as session:
            stmt = select(Workspace)
            if workspace:
                stmt = stmt.where(
                    or_(Workspace.id == workspace, Workspace.name == workspace)
                )
            found = (await session.execute(stmt)).scalars().all()
        if not found:
            raise CLIError(
                f"Workspace {workspace!r} not found"
                if workspace
                else "No workspace exists yet; sign up first"
            )
        if len(found) > 1:
            names = ", ".join(w.name for w in found)
            raise CLIError(f"Several workspaces exist ({names}); pass --workspace")
        return cls(found[0].id, owns_engine)

    async def import_suite(self, text: str, fmt: str) -> dict[str, Any]:
        from llmwatch.db.engine import get_sessionmaker
        from llmwatch.evals import suites as suite_service
        from llmwatch.evals.schema import parse_suite

        definition = parse_suite(text, fmt)
        async with get_sessionmaker()() as session:
            repo = suite_service.SuiteRepository(session, self.workspace_id)
            suite = await repo.by_name(definition.name)
            if suite is None:
                suite = await suite_service.create_suite(
                    session, self.workspace_id, definition
                )
                created = True
            else:
                _, created = await suite_service.save_new_version(
                    session, suite, definition
                )
            await session.commit()
            return {
                "id": suite.id,
                "name": suite.name,
                "latest_version": suite.latest_version,
                "baseline_run_id": suite.baseline_run_id,
                "created_version": created,
            }

    async def start_runs(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        from llmwatch.db.engine import get_sessionmaker
        from llmwatch.evals import runner
        from llmwatch.routers.evals import run_out

        async with get_sessionmaker()() as session:
            runs = await runner.create_runs(
                session,
                self.workspace_id,
                suite_id=body["suite_id"],
                variants=[
                    runner.VariantSpec(
                        model=v["model"],
                        params=v.get("params", {}),
                        thinking=v.get("thinking", False),
                    )
                    for v in body["variants"]
                ],
                repeats=body["repeats"],
                concurrency=body["concurrency"],
                judge_model=body.get("judge_model"),
                embedding_model=body.get("embedding_model"),
                use_cache=body["use_cache"],
            )
            await session.commit()
            return [run_out(r) for r in runs]

    async def wait_run(self, run_id: str) -> dict[str, Any]:
        from llmwatch.db.engine import get_sessionmaker
        from llmwatch.db.models import EvalRun
        from llmwatch.evals.runner import RunExecutor
        from llmwatch.routers.evals import run_out

        await RunExecutor(run_id, self.workspace_id).execute()
        async with get_sessionmaker()() as session:
            return run_out(await session.get(EvalRun, run_id))

    async def compare(self, baseline: str, candidate: str) -> dict[str, Any]:
        from llmwatch.db.engine import get_sessionmaker
        from llmwatch.evals.compare import compare_runs

        async with get_sessionmaker()() as session:
            return await compare_runs(session, self.workspace_id, baseline, candidate)

    async def set_baseline(self, suite_id: str, run_id: str) -> None:
        from llmwatch.db.engine import get_sessionmaker
        from llmwatch.db.models import EvalSuite

        async with get_sessionmaker()() as session:
            suite = await session.get(EvalSuite, suite_id)
            suite.baseline_run_id = run_id
            await session.commit()

    async def close(self) -> None:
        from llmwatch.db.engine import dispose_engine

        if self._owns_engine:
            await dispose_engine()


# ── Server backend ──────────────────────────────────────────


def make_http_client(server: str, api_key: str):
    """Builds the HTTP client (tests swap this for an in-process transport)."""
    import httpx

    return httpx.AsyncClient(
        base_url=server.rstrip("/"), headers={"X-API-Key": api_key}, timeout=60.0
    )


class ServerBackend:
    def __init__(self, server: str, api_key: str, poll_interval: float = 2.0):
        self.http = make_http_client(server, api_key)
        self.poll_interval = poll_interval

    async def _call(self, method: str, path: str, **kwargs) -> Any:
        resp = await self.http.request(method, path, **kwargs)
        if resp.status_code >= 400:
            try:
                message = resp.json().get("error") or resp.json().get("detail")
            except ValueError:
                message = resp.text[:300]
            raise CLIError(f"{method} {path} failed ({resp.status_code}): {message}")
        return resp.json() if resp.content else None

    async def import_suite(self, text: str, fmt: str) -> dict[str, Any]:
        return await self._call(
            "POST", "/evals/suites/import", json={"content": text, "format": fmt}
        )

    async def start_runs(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        payload = dict(body)
        payload["variants"] = [
            {
                "model": v["model"],
                "thinking": v.get("thinking", False),
                **v.get("params", {}),
            }
            for v in body["variants"]
        ]
        return (await self._call("POST", "/evals/runs", json=payload))["runs"]

    async def wait_run(self, run_id: str) -> dict[str, Any]:
        while True:
            run = await self._call("GET", f"/evals/runs/{run_id}")
            if run["status"] not in ("pending", "running", "cancelling"):
                return run
            await asyncio.sleep(self.poll_interval)

    async def compare(self, baseline: str, candidate: str) -> dict[str, Any]:
        return await self._call(
            "GET",
            "/evals/compare",
            params={"baseline": baseline, "candidate": candidate},
        )

    async def set_baseline(self, suite_id: str, run_id: str) -> None:
        await self._call(
            "PUT", f"/evals/suites/{suite_id}/baseline", json={"run_id": run_id}
        )

    async def close(self) -> None:
        await self.http.aclose()


# ── Commands ────────────────────────────────────────────────


def _parse_params(items: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    allowed = {"temperature", "max_tokens", "top_p", "seed"}
    for item in items or []:
        key, sep, raw = item.partition("=")
        if not sep or key not in allowed:
            raise CLIError(
                f"--param must be one of {sorted(allowed)} as key=value, got {item!r}"
            )
        try:
            params[key] = json.loads(raw)
        except json.JSONDecodeError:
            raise CLIError(f"--param {key} needs a number, got {raw!r}") from None
    return params


def _fmt(value: float | None, pattern: str, missing: str = "-") -> str:
    return missing if value is None else pattern.format(value)


def _print_run(run: dict[str, Any], out) -> None:
    print(
        f"  {run['label']:<40} {run['status']:<10} "
        f"pass {_fmt(run['pass_rate'], '{:.1%}'):>6}  "
        f"score {_fmt(run['mean_score'], '{:.3f}'):>5}  "
        f"cost ${run['total_cost_usd']:.6f}  "
        f"errors {run['failed_items']}/{run['total_items']}",
        file=out,
    )


def _print_comparison(c: dict[str, Any], out) -> None:
    s, p = c["score"], c["pass_rate"]
    verdict = {
        "improved": "IMPROVED",
        "regressed": "REGRESSED",
        "no_significant_difference": "no significant difference",
    }[c["verdict"]]
    print(
        f"\n  {c['candidate']['label']} vs baseline {c['baseline']['label']}", file=out
    )
    print(
        f"    score delta {s['delta']:+.3f}  "
        f"95% CI [{s['ci_low']:+.3f}, {s['ci_high']:+.3f}]  "
        f"{'significant' if s['significant'] else 'not significant'}",
        file=out,
    )
    print(
        f"    pass rate {p['baseline']:.1%} -> {p['candidate']:.1%}  "
        f"(fixed {p['fixes']}, regressed {p['regressions']}, McNemar p={p['p_value']:.4f})",
        file=out,
    )
    cost = c["cost"]
    if cost["delta_pct"] is not None:
        print(f"    cost per case {cost['delta_pct']:+.1f}%", file=out)
    print(f"    verdict: {verdict}", file=out)
    for warning in c.get("warnings", []):
        print(f"    note: {warning}", file=out)


async def _open_backend(args) -> Backend:
    if args.server:
        if not args.api_key:
            raise CLIError("--server needs --api-key (or LLMWATCH_API_KEY)")
        return ServerBackend(args.server, args.api_key, args.poll_interval)
    return await LocalBackend.connect(args.workspace)


async def eval_run(args, out=sys.stdout, err=sys.stderr) -> int:
    path = Path(args.suite)
    if not path.is_file():
        raise CLIError(f"Suite file not found: {path}")
    fmt = "json" if path.suffix.lower() == ".json" else "yaml"
    text = path.read_text()
    from llmwatch.evals.schema import SuiteFormatError, parse_suite

    try:
        parse_suite(text, fmt)  # fail fast, before touching a server or database
    except SuiteFormatError as exc:
        raise CLIError(str(exc)) from exc

    backend = await _open_backend(args)
    try:
        suite = await backend.import_suite(text, fmt)
        if not args.json:
            note = "new version" if suite.get("created_version") else "unchanged"
            print(
                f"Suite {suite['name']} v{suite['latest_version']} ({note})", file=out
            )
        params = _parse_params(args.param)
        runs = await backend.start_runs(
            {
                "suite_id": suite["id"],
                "variants": [
                    {"model": m, "params": params, "thinking": args.thinking}
                    for m in args.model
                ],
                "repeats": args.repeats,
                "concurrency": args.concurrency,
                "judge_model": args.judge_model,
                "embedding_model": args.embedding_model,
                "use_cache": not args.no_cache,
            }
        )
        finished = [await backend.wait_run(r["id"]) for r in runs]
        if not args.json:
            print("Runs:", file=out)
            for run in finished:
                _print_run(run, out)

        baseline = args.baseline
        if baseline == "suite":
            baseline = suite.get("baseline_run_id")
            if baseline is None and not args.json:
                print("\nThe suite has no baseline yet; nothing to compare.", file=out)
        comparisons = []
        if baseline:
            for run in finished:
                if run["status"] == "completed" and run["id"] != baseline:
                    comparisons.append(await backend.compare(baseline, run["id"]))
        if not args.json:
            for c in comparisons:
                _print_comparison(c, out)

        failed = [r for r in finished if r["status"] != "completed"]
        regressed = [c for c in comparisons if c["verdict"] == "regressed"]
        if failed:
            code = EXIT_ERROR
        elif regressed and args.fail_on_regression:
            code = EXIT_REGRESSION
        else:
            code = EXIT_OK

        if args.set_baseline and not failed and not regressed:
            await backend.set_baseline(suite["id"], finished[0]["id"])
            if not args.json:
                print(
                    f"\nMarked run {finished[0]['id']} as the suite baseline.", file=out
                )

        if args.json:
            json.dump(
                {
                    "suite": suite,
                    "runs": finished,
                    "comparisons": comparisons,
                    "exit_code": code,
                },
                out,
                indent=2,
                default=str,
            )
            print(file=out)
        elif failed:
            print(f"\n{len(failed)} run(s) did not complete.", file=err)
        elif regressed and args.fail_on_regression:
            print("\nSignificant regression detected.", file=err)
        return code
    finally:
        await backend.close()


async def eval_compare(args, out=sys.stdout, err=sys.stderr) -> int:
    backend = await _open_backend(args)
    try:
        comparison = await backend.compare(args.baseline, args.candidate)
    finally:
        await backend.close()
    if args.json:
        json.dump(comparison, out, indent=2, default=str)
        print(file=out)
    else:
        _print_comparison(comparison, out)
    if comparison["verdict"] == "regressed" and args.fail_on_regression:
        return EXIT_REGRESSION
    return EXIT_OK


def add_eval_commands(sub) -> None:
    import os

    def common(p):
        p.add_argument("--server", help="Server URL (default: use the local database)")
        p.add_argument(
            "--api-key",
            default=os.environ.get("LLMWATCH_API_KEY"),
            help="API key for --server (default: $LLMWATCH_API_KEY)",
        )
        p.add_argument("--workspace", help="Workspace name or id (local mode)")
        p.add_argument("--json", action="store_true", help="Machine-readable output")
        p.add_argument(
            "--fail-on-regression",
            action="store_true",
            help="Exit 1 if a comparison shows a significant regression",
        )
        p.add_argument(
            "--poll-interval", type=float, default=2.0, help=argparse.SUPPRESS
        )

    eval_parser = sub.add_parser("eval", help="Run and compare eval suites")
    eval_sub = eval_parser.add_subparsers(dest="eval_command", required=True)

    run = eval_sub.add_parser("run", help="Run a suite file against one or more models")
    run.add_argument("suite", help="Suite file (.yaml, .yml or .json)")
    run.add_argument(
        "--model", action="append", required=True, help="Model reference (repeatable)"
    )
    run.add_argument(
        "--param",
        action="append",
        default=[],
        help="temperature/max_tokens/top_p/seed=value",
    )
    run.add_argument("--repeats", type=int, default=1)
    run.add_argument("--concurrency", type=int, default=4)
    run.add_argument("--judge-model", help="Default model for llm_judge assertions")
    run.add_argument(
        "--embedding-model", help="Default model for similarity assertions"
    )
    run.add_argument("--no-cache", action="store_true", help="Always call the model")
    run.add_argument(
        "--thinking",
        action="store_true",
        help="Let reasoning models think (off by default)",
    )
    run.add_argument(
        "--baseline",
        help="Run id to compare against, or 'suite' for the suite's baseline",
    )
    run.add_argument(
        "--set-baseline",
        action="store_true",
        help="Mark the (first) new run as the suite baseline if nothing regressed",
    )
    common(run)
    run.set_defaults(eval_func=eval_run)

    compare = eval_sub.add_parser("compare", help="Compare two runs")
    compare.add_argument("baseline")
    compare.add_argument("candidate")
    common(compare)
    compare.set_defaults(eval_func=eval_compare)


async def run_eval_command(args, out=sys.stdout, err=sys.stderr) -> int:
    """Runs `eval ...` and maps errors to exit code 2 with a readable message."""
    from llmwatch.exceptions import LLMWatchException

    try:
        return await args.eval_func(args, out, err)
    except CLIError as exc:
        print(f"error: {exc}", file=err)
    except LLMWatchException as exc:
        print(f"error: {exc.message}", file=err)
    return EXIT_ERROR
