"""
Module: schema.py (evals)
Purpose: The eval suite definition: the YAML/JSON file format and the API body.
WHY: One validated shape for suites created in the UI, imported from files, or sent
by the CLI. Validation catches mistakes before a run spends money: duplicate case
ids, cases missing template variables, malformed assertions.

Example (YAML):

    name: support-triage
    description: Route support tickets to the right queue
    system_prompt: You are a support triage assistant.
    prompt: |
      Classify this ticket into billing, bug or account.
      Ticket: {{ ticket }}
    assert:                 # applied to every case
      - type: latency_under
        value: 5000
    cases:
      - id: refund-request
        vars: {ticket: "I was charged twice"}
        expected: billing
        assert:
          - type: contains
            value: billing
        tags: [billing]
"""

import json
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from llmwatch.evals.template import variables

MAX_CASES = 5000


class SuiteFormatError(ValueError):
    """The suite file can't be parsed or doesn't match the schema."""


class Assertion(BaseModel):
    """One check on a model output. `type` picks the evaluator; `value` and any
    other keys are its configuration (see llmwatch.evals.evaluators)."""

    model_config = ConfigDict(extra="allow")
    type: str = Field(..., min_length=1, max_length=50)
    value: Any = None
    # Relative weight in the case score (default 1).
    weight: float = Field(1.0, gt=0, le=100)

    def config(self) -> dict[str, Any]:
        """Evaluator-specific options (everything except type/value/weight)."""
        return dict(self.model_extra or {})


class CaseDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # Stable id used to pair cases across versions and runs.
    id: str | None = Field(None, min_length=1, max_length=200)
    vars: dict[str, Any] = Field(default_factory=dict)
    expected: str | None = None
    assertions: list[Assertion] = Field(default_factory=list, alias="assert")
    tags: list[str] = Field(default_factory=list)


class SuiteDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=5000)
    prompt: str = Field(..., min_length=1, max_length=100_000)
    system_prompt: str | None = Field(None, max_length=50_000)
    default_assertions: list[Assertion] = Field(default_factory=list, alias="assert")
    cases: list[CaseDefinition] = Field(..., min_length=1, max_length=MAX_CASES)

    @model_validator(mode="after")
    def _check_cases(self) -> "SuiteDefinition":
        used = set(variables(self.prompt)) | set(variables(self.system_prompt or ""))
        seen: set[str] = set()
        problems: list[str] = []
        for i, case in enumerate(self.cases, 1):
            case.id = case.id or f"case-{i}"
            if case.id in seen:
                problems.append(f"duplicate case id {case.id!r}")
            seen.add(case.id)
            missing = sorted(used - set(case.vars))
            if missing:
                problems.append(
                    f"case {case.id!r} is missing vars: {', '.join(missing)}"
                )
            if len(problems) >= 20:
                break
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def to_document(self) -> dict[str, Any]:
        """The canonical file form (keys in a readable order, empty bits left out)."""
        doc: dict[str, Any] = {"name": self.name}
        if self.description:
            doc["description"] = self.description
        if self.system_prompt:
            doc["system_prompt"] = self.system_prompt
        doc["prompt"] = self.prompt
        if self.default_assertions:
            doc["assert"] = [_assertion_doc(a) for a in self.default_assertions]
        doc["cases"] = []
        for case in self.cases:
            item: dict[str, Any] = {"id": case.id, "vars": case.vars}
            if case.expected is not None:
                item["expected"] = case.expected
            if case.assertions:
                item["assert"] = [_assertion_doc(a) for a in case.assertions]
            if case.tags:
                item["tags"] = case.tags
            doc["cases"].append(item)
        return doc

    def content_hash_input(self) -> str:
        """Canonical JSON of everything a version snapshots (not name/description)."""
        doc = self.to_document()
        doc.pop("name", None)
        doc.pop("description", None)
        return json.dumps(doc, sort_keys=True, ensure_ascii=False)


def _assertion_doc(a: Assertion) -> dict[str, Any]:
    doc: dict[str, Any] = {"type": a.type}
    if a.value is not None:
        doc["value"] = a.value
    if a.weight != 1.0:
        doc["weight"] = a.weight
    doc.update(a.config())
    return doc


def parse_suite(text: str, fmt: str = "yaml") -> SuiteDefinition:
    """Parses a suite file. YAML is loaded with safe_load (no object construction)."""
    try:
        data = yaml.safe_load(text) if fmt == "yaml" else json.loads(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise SuiteFormatError(f"Could not parse {fmt.upper()}: {exc}") from exc
    if not isinstance(data, dict):
        raise SuiteFormatError(
            "A suite file must be a mapping with name, prompt, cases"
        )
    try:
        return SuiteDefinition.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'suite'}: {err['msg']}"
            for err in exc.errors()[:10]
        )
        raise SuiteFormatError(f"Invalid suite: {details}") from exc


def dump_suite(suite: SuiteDefinition, fmt: str = "yaml") -> str:
    doc = suite.to_document()
    if fmt == "json":
        return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)
