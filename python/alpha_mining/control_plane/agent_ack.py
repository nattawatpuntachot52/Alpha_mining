"""Parse and validate structured AGENT_ACK runtime/environment disclosures."""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass

REQUIRED_ACK_FIELDS: tuple[str, ...] = (
    "mission_id",
    "task_id",
    "agent_id",
    "actual_provider_runtime",
    "actual_model_id_version",
    "mutation_boundary",
    "verification_summary",
)

TEMPLATE_OPTIONAL_FIELDS: tuple[str, ...] = (
    "assignment_id",
    "phase_id",
    "ovca_role",
    "tools_environment",
)

ALLOWED_OVCA_ROLES: tuple[str, ...] = (
    "front_door_conditioner",
    "coordinator",
    "engineer",
    "verifier",
    "reviewer",
    "auditor",
)

_EMBEDDED_PLACEHOLDER_RE = re.compile(r"<[^>\s][^>]*>")
_GUESS_WORDS_RE = re.compile(r"\b(probably|maybe|guess)\b|น่าจะ", re.IGNORECASE)
_FENCED_BLOCK_RE = re.compile(r"```(?:text|txt|md|markdown|yaml|yml)?[ \t]*\n(.*?)\n[ \t]*```", re.DOTALL)


@dataclass(frozen=True)
class AgentAckReport:
    present: bool
    valid: bool
    fields: dict[str, str]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def _extract_ack_lines(markdown_text: str) -> list[str] | None:
    """Locate an AGENT_ACK block inside fenced code blocks or raw markdown text."""
    for match in _FENCED_BLOCK_RE.finditer(markdown_text):
        dedented = textwrap.dedent(match.group(1))
        lines = dedented.splitlines()
        for idx, line in enumerate(lines):
            if line.strip() == "AGENT_ACK":
                tail_block = textwrap.dedent("\n".join(lines[idx + 1 :]))
                return tail_block.splitlines() if tail_block else []

    lines = markdown_text.splitlines()
    for idx, line in enumerate(lines):
        if line.strip() == "AGENT_ACK":
            collected: list[str] = []
            for tail in lines[idx + 1 :]:
                stripped = tail.strip()
                if stripped.startswith("#") or stripped.startswith("```"):
                    break
                if stripped == "" and collected:
                    break
                collected.append(tail)
            if not collected:
                return []
            block = textwrap.dedent("\n".join(collected))
            return block.splitlines()
    return None


def parse_agent_ack(markdown_text: str) -> dict[str, str]:
    """Parse key-value entries (and nested indented sublines) from an AGENT_ACK block."""
    raw_lines = _extract_ack_lines(markdown_text)
    if raw_lines is None:
        return {}

    fields: dict[str, str] = {}
    current_key: str | None = None
    for line in raw_lines:
        if not line.strip():
            continue
        if line.startswith((" ", "\t")) and current_key is not None:
            existing = fields.get(current_key, "")
            sub = line.strip()
            fields[current_key] = f"{existing}; {sub}" if existing else sub
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            norm_key = key.strip()
            if norm_key:
                fields[norm_key] = val.strip()
                current_key = norm_key
    return fields


def _validate_field_value(key: str, val: str, errors: list[str]) -> None:
    if not val:
        errors.append(f"AGENT_ACK field '{key}' is empty or missing")
        return
    if _EMBEDDED_PLACEHOLDER_RE.search(val) or val.upper() in ("TBD", "TODO", "N/A"):
        errors.append(f"AGENT_ACK field '{key}' contains unreplaced placeholder '{val}'")
    if _GUESS_WORDS_RE.search(val):
        errors.append(f"AGENT_ACK field '{key}' contains disallowed guess language: '{val}'")


def validate_agent_ack(markdown_text: str) -> AgentAckReport:
    """Validate AGENT_ACK completeness and anti-guess honesty constraints."""
    raw_lines = _extract_ack_lines(markdown_text)
    if raw_lines is None:
        return AgentAckReport(
            present=False,
            valid=False,
            fields={},
            errors=("missing AGENT_ACK block",),
            warnings=(),
        )

    fields = parse_agent_ack(markdown_text)
    if not fields:
        return AgentAckReport(
            present=True,
            valid=False,
            fields={},
            errors=("empty AGENT_ACK block",),
            warnings=(),
        )

    errors: list[str] = []
    warnings: list[str] = []

    for req in REQUIRED_ACK_FIELDS:
        _validate_field_value(req, fields.get(req, "").strip(), errors)

    for opt in TEMPLATE_OPTIONAL_FIELDS:
        if opt in fields:
            val = fields[opt].strip()
            _validate_field_value(opt, val, errors)
            if opt == "ovca_role" and val and not _EMBEDDED_PLACEHOLDER_RE.search(val):
                if val.lower() not in ALLOWED_OVCA_ROLES:
                    errors.append(
                        f"AGENT_ACK field 'ovca_role' must be one of {ALLOWED_OVCA_ROLES}, got '{val}'"
                    )

    model_val = fields.get("actual_model_id_version", "").strip()
    if model_val and "UNKNOWN" not in model_val.upper() and len(model_val) < 3:
        warnings.append("actual_model_id_version looks unusually short; verify runtime exposure")

    ver_summary = fields.get("verification_summary", "").lower()
    if "not run" in ver_summary or "failed" in ver_summary:
        warnings.append("AGENT_ACK verification_summary discloses unverified or failed checks")

    return AgentAckReport(
        present=True,
        valid=len(errors) == 0,
        fields=fields,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
