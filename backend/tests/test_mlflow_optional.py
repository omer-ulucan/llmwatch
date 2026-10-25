"""
MLflow is optional: off unless MLFLOW_TRACKING_URI is set, and never required.
"""

import builtins
import logging
import sys
import types

from llmwatch.config import settings
from llmwatch.services.mlflow_service import MLFlowService

CALL = dict(
    company_id="ws",
    model_name="m",
    thinking_mode=False,
    prompt_length=3,
    latency_ms=1.5,
    input_tokens=1,
    output_tokens=1,
    cost_usd=0.0,
    success=True,
    prompt_preview="hi",
    response_preview="ho",
)


def test_disabled_without_tracking_uri(monkeypatch):
    monkeypatch.setattr(settings, "mlflow_tracking_uri", "")
    real_import = builtins.__import__

    def no_mlflow(name, *args, **kwargs):
        assert name != "mlflow", "mlflow must not be imported when disabled"
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_mlflow)
    svc = MLFlowService()
    assert svc.enabled is False
    svc.log_llm_call(**CALL)  # no-op, no error


def test_uri_without_mlflow_installed_warns_and_disables(monkeypatch, caplog):
    monkeypatch.setattr(settings, "mlflow_tracking_uri", "http://mlflow:5000")
    monkeypatch.setitem(sys.modules, "mlflow", None)  # makes `import mlflow` fail
    with caplog.at_level(logging.WARNING, logger="llmwatch"):
        svc = MLFlowService()
    assert svc.enabled is False
    assert "mlflow is not installed" in caplog.text
    svc.log_llm_call(**CALL)


def test_enabled_when_uri_set_and_installed(monkeypatch):
    calls = []
    fake = types.ModuleType("mlflow")
    fake.set_tracking_uri = lambda uri: calls.append(("uri", uri))
    fake.set_experiment = lambda name: calls.append(("experiment", name))

    class _Run:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    fake.start_run = lambda run_name: _Run()
    fake.log_params = lambda p: calls.append(("params", p))
    fake.log_metrics = lambda m: calls.append(("metrics", m))
    fake.log_tags = lambda t: calls.append(("tags", t))
    monkeypatch.setitem(sys.modules, "mlflow", fake)
    monkeypatch.setattr(settings, "mlflow_tracking_uri", "http://mlflow:5000")

    svc = MLFlowService()
    svc.log_llm_call(**CALL)

    assert svc.enabled is True
    assert ("uri", "http://mlflow:5000") in calls
    assert ("experiment", "llmwatch_ws") in calls
    metrics = dict(next(v for k, v in calls if k == "metrics"))
    assert metrics["latency_ms"] == 1.5
