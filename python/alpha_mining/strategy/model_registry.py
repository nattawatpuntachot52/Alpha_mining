"""Atomic trading model registry validator and deterministic MQL5 portfolio assembler.

Enforces single-source-of-truth isolation across `models/{alpha,beta,omega}/`:
- Globally unique `model_id`, `magic_number`, and `mql5.prefix`.
- Exact Magic Number parity across `registry.json`, `spec.json`, and `module.mqh`.
- Presence of the 4 standardized MQL5 lifecycle hooks in every `module.mqh`.
- Deterministic, zero-drift single-file `.mq5` portfolio and standalone assembly.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ALLOWED_CATEGORIES = frozenset({"alpha", "beta", "omega"})
ALLOWED_EVIDENCE_STATUSES = frozenset(
    {
        "proposed",
        "exploratory",
        "reproducible",
        "robustness_validated",
        "independently_replicated",
    }
)
ALLOWED_DIRECTIONS = frozenset({"long_only", "short_only", "long_short"})

_MODEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_PORTFOLIO_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_MQL5_PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
_EA_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


class ModelRegistryError(ValueError):
    """Raised when a model registry, model spec, module, or portfolio manifest is invalid."""


@dataclass(frozen=True)
class ModelRecord:
    model_id: str
    category: str
    display_name: str
    version: str
    evidence_status: str
    drive_vault_folder_key: str
    mql5_prefix: str
    magic_number: int
    timeframe: str
    direction: str
    default_lot: float
    hedging_required: bool
    summary: str
    spec_path: Path
    module_path: Path
    spec_sha256: str
    module_sha256: str
    combined_sha256: str


@dataclass(frozen=True)
class ModelRegistry:
    repo_root: Path
    registry_path: Path
    core_helpers_path: Path
    core_helpers_sha256: str
    categories: dict[str, dict[str, Any]]
    models: tuple[ModelRecord, ...]

    def get(self, model_id: str) -> ModelRecord:
        for record in self.models:
            if record.model_id == model_id:
                return record
        raise ModelRegistryError(f"unknown model_id {model_id!r}")


@dataclass(frozen=True)
class PortfolioSlot:
    model_id: str
    enabled: bool
    default_lot: float


@dataclass(frozen=True)
class PortfolioSpec:
    portfolio_id: str
    ea_name: str
    description: str
    account_lock: int
    disable_check_interval_seconds: int
    output_path: str | None
    slots: tuple[PortfolioSlot, ...]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _resolve_under_root(repo_root: Path, rel_path: str, label: str) -> Path:
    if not isinstance(rel_path, str) or not rel_path.strip():
        raise ModelRegistryError(f"{label} must be a non-empty relative path string")
    if rel_path.startswith(("/", "\\")):
        raise ModelRegistryError(f"{label} must be relative to repo root, got {rel_path!r}")
    root_resolved = repo_root.resolve()
    candidate = (root_resolved / rel_path).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ModelRegistryError(f"{label} escapes repository root: {rel_path!r}") from exc
    return candidate


def _require_non_bool_int(value: Any, field_name: str, *, min_value: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelRegistryError(f"{field_name} must be an integer, got {value!r}")
    if value < min_value:
        raise ModelRegistryError(f"{field_name} must be >= {min_value}, got {value}")
    return value


def _require_finite_float(value: Any, field_name: str, *, min_value: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelRegistryError(f"{field_name} must be numeric, got {value!r}")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < min_value:
        raise ModelRegistryError(f"{field_name} must be finite and >= {min_value}, got {value!r}")
    return parsed


def _strip_mql5_comments_and_strings(source: str) -> str:
    """Strip C/MQL5 comments and double-quoted string literals for structural checks."""
    out: list[str] = []
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            i += 2
            while i < n and source[i] != "\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < n and not (source[i] == "*" and source[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if ch == '"':
            i += 1
            while i < n:
                if source[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if source[i] == '"':
                    i += 1
                    break
                i += 1
            out.append('""')
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _check_balanced_braces(source: str, label: str) -> None:
    cleaned = _strip_mql5_comments_and_strings(source)
    depth = 0
    for ch in cleaned:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                raise ModelRegistryError(f"unbalanced closing brace '}}' in {label}")
    if depth != 0:
        raise ModelRegistryError(f"unbalanced braces in {label}: net depth {depth}")


def _validate_module_source(
    source: str,
    *,
    prefix: str,
    magic_number: int,
    label: str,
) -> None:
    _check_balanced_braces(source, label)
    cleaned = _strip_mql5_comments_and_strings(source)

    magic_macro = f"MAGIC_{prefix.upper()}"
    magic_re = re.compile(rf"^\s*#define\s+{re.escape(magic_macro)}\s+(\d+)\b", re.MULTILINE)
    matches = magic_re.findall(cleaned)
    if not matches:
        raise ModelRegistryError(
            f"{label} missing required macro '#define {magic_macro} {magic_number}'"
        )
    if len(matches) > 1:
        raise ModelRegistryError(f"{label} defines {magic_macro} multiple times")
    found_magic = int(matches[0])
    if found_magic != magic_number:
        raise ModelRegistryError(
            f"{label} macro {magic_macro}={found_magic} does not match spec/registry magic_number={magic_number}"
        )

    required_hooks = (
        (f"Init_{prefix}", rf"\bvoid\s+Init_{re.escape(prefix)}\s*\(\s*\)"),
        (f"LogConfig_{prefix}", rf"\bvoid\s+LogConfig_{re.escape(prefix)}\s*\(\s*\)"),
        (
            f"EnforceDisabled_{prefix}",
            rf"\bvoid\s+EnforceDisabled_{re.escape(prefix)}\s*\(\s*bool\s+\w+\s*,\s*double\s+\w+\s*\)",
        ),
        (
            f"Process_{prefix}",
            rf"\bvoid\s+Process_{re.escape(prefix)}\s*\(\s*bool\s+\w+\s*,\s*double\s+\w+\s*\)",
        ),
    )
    for hook_name, pattern in required_hooks:
        if not re.search(pattern, cleaned):
            raise ModelRegistryError(
                f"{label} missing required MQL5 lifecycle hook '{hook_name}'"
            )


def load_and_validate_registry(
    repo_root: Path,
    registry_rel_path: str = "models/registry.json",
) -> ModelRegistry:
    """Load and validate models/registry.json, all model specs, modules, and orphan checks."""
    root = repo_root.resolve()
    registry_path = _resolve_under_root(root, registry_rel_path, "registry_path")
    if not registry_path.is_file():
        raise ModelRegistryError(f"model registry not found: {registry_path}")

    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ModelRegistryError(f"invalid JSON in {registry_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ModelRegistryError("registry root must be a JSON object")
    if raw.get("schema_version") != "1.0":
        raise ModelRegistryError(f"unsupported registry schema_version: {raw.get('schema_version')!r}")

    core_rel = raw.get("core_mql5_helpers")
    core_path = _resolve_under_root(root, core_rel, "core_mql5_helpers")
    if not core_path.is_file():
        raise ModelRegistryError(f"core_mql5_helpers file not found: {core_path}")
    core_bytes = core_path.read_bytes()
    _check_balanced_braces(core_bytes.decode("utf-8"), str(core_rel))

    raw_categories = raw.get("categories")
    if not isinstance(raw_categories, dict) or set(raw_categories.keys()) != ALLOWED_CATEGORIES:
        raise ModelRegistryError(
            f"registry categories must define exactly {sorted(ALLOWED_CATEGORIES)}"
        )

    raw_models = raw.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise ModelRegistryError("registry 'models' must be a non-empty list")

    seen_ids: set[str] = set()
    seen_magics: set[int] = set()
    seen_prefixes: set[str] = set()
    registered_spec_paths: set[Path] = set()
    records: list[ModelRecord] = []

    for idx, entry in enumerate(raw_models):
        if not isinstance(entry, dict):
            raise ModelRegistryError(f"registry models[{idx}] must be an object")

        model_id = entry.get("model_id")
        if not isinstance(model_id, str) or not _MODEL_ID_RE.fullmatch(model_id):
            raise ModelRegistryError(f"invalid model_id at models[{idx}]: {model_id!r}")
        if model_id in seen_ids:
            raise ModelRegistryError(f"duplicate model_id in registry: {model_id!r}")
        seen_ids.add(model_id)

        category = entry.get("category")
        if category not in ALLOWED_CATEGORIES:
            raise ModelRegistryError(f"invalid category for {model_id!r}: {category!r}")

        reg_magic = _require_non_bool_int(entry.get("magic_number"), f"{model_id}.magic_number", min_value=1)
        if reg_magic in seen_magics:
            raise ModelRegistryError(f"duplicate magic_number {reg_magic} for model {model_id!r}")
        seen_magics.add(reg_magic)

        reg_prefix = entry.get("mql5_prefix")
        if not isinstance(reg_prefix, str) or not _MQL5_PREFIX_RE.fullmatch(reg_prefix):
            raise ModelRegistryError(f"invalid mql5_prefix for {model_id!r}: {reg_prefix!r}")
        if reg_prefix.lower() in seen_prefixes:
            raise ModelRegistryError(f"duplicate mql5_prefix {reg_prefix!r} for model {model_id!r}")
        seen_prefixes.add(reg_prefix.lower())

        spec_rel = entry.get("spec_path")
        spec_path = _resolve_under_root(root, spec_rel, f"{model_id}.spec_path")
        if not spec_path.is_file():
            raise ModelRegistryError(f"spec file not found for {model_id!r}: {spec_path}")
        registered_spec_paths.add(spec_path)

        spec_bytes = spec_path.read_bytes()
        try:
            spec = json.loads(spec_bytes.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ModelRegistryError(f"invalid JSON in {spec_path}: {exc}") from exc
        if not isinstance(spec, dict):
            raise ModelRegistryError(f"{spec_path} must be a JSON object")

        if spec.get("schema_version") != "1.0":
            raise ModelRegistryError(f"{model_id}: unsupported spec schema_version {spec.get('schema_version')!r}")
        if spec.get("model_id") != model_id:
            raise ModelRegistryError(f"{model_id}: spec model_id {spec.get('model_id')!r} mismatches registry")
        if spec.get("category") != category:
            raise ModelRegistryError(f"{model_id}: spec category {spec.get('category')!r} mismatches registry")

        evidence_status = spec.get("evidence_status")
        if evidence_status not in ALLOWED_EVIDENCE_STATUSES:
            raise ModelRegistryError(
                f"{model_id}: invalid evidence_status {evidence_status!r}; allowed={sorted(ALLOWED_EVIDENCE_STATUSES)}"
            )

        display_name = spec.get("display_name")
        version = spec.get("version")
        drive_folder_key = spec.get("drive_vault_folder_key")
        for field_name, val in (
            ("display_name", display_name),
            ("version", version),
            ("drive_vault_folder_key", drive_folder_key),
        ):
            if not isinstance(val, str) or not val.strip():
                raise ModelRegistryError(f"{model_id}: spec.{field_name} must be a non-empty string")

        mql5 = spec.get("mql5")
        if not isinstance(mql5, dict):
            raise ModelRegistryError(f"{model_id}: spec.mql5 must be an object")

        spec_prefix = mql5.get("prefix")
        if spec_prefix != reg_prefix:
            raise ModelRegistryError(
                f"{model_id}: spec.mql5.prefix {spec_prefix!r} mismatches registry mql5_prefix {reg_prefix!r}"
            )
        spec_magic = _require_non_bool_int(mql5.get("magic_number"), f"{model_id}.mql5.magic_number", min_value=1)
        if spec_magic != reg_magic:
            raise ModelRegistryError(
                f"{model_id}: spec.mql5.magic_number {spec_magic} mismatches registry magic_number {reg_magic}"
            )

        timeframe = mql5.get("timeframe")
        if not isinstance(timeframe, str) or not timeframe.startswith("PERIOD_"):
            raise ModelRegistryError(f"{model_id}: invalid mql5.timeframe {timeframe!r}")
        direction = mql5.get("direction")
        if direction not in ALLOWED_DIRECTIONS:
            raise ModelRegistryError(f"{model_id}: invalid mql5.direction {direction!r}")
        default_lot = _require_finite_float(mql5.get("default_lot"), f"{model_id}.mql5.default_lot", min_value=0.0)
        hedging_required = mql5.get("hedging_required")
        if not isinstance(hedging_required, bool):
            raise ModelRegistryError(f"{model_id}: mql5.hedging_required must be a boolean")

        module_file = mql5.get("module_file")
        if not isinstance(module_file, str) or "/" in module_file or "\\" in module_file or not module_file.endswith(".mqh"):
            raise ModelRegistryError(f"{model_id}: mql5.module_file must be a local .mqh filename, got {module_file!r}")
        module_path = (spec_path.parent / module_file).resolve()
        try:
            module_path.relative_to(spec_path.parent.resolve())
        except ValueError as exc:
            raise ModelRegistryError(f"{model_id}: module_file escapes model directory") from exc
        if not module_path.is_file():
            raise ModelRegistryError(f"{model_id}: module file not found: {module_path}")

        module_bytes = module_path.read_bytes()
        _validate_module_source(
            module_bytes.decode("utf-8"),
            prefix=reg_prefix,
            magic_number=reg_magic,
            label=str(module_path.relative_to(root)),
        )

        logic = spec.get("logic")
        if not isinstance(logic, dict):
            raise ModelRegistryError(f"{model_id}: spec.logic must be an object")
        summary = logic.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ModelRegistryError(f"{model_id}: spec.logic.summary must be a non-empty string")
        for list_field in ("known_assumptions", "rejection_criteria"):
            val = logic.get(list_field)
            if not isinstance(val, list) or not val or not all(isinstance(x, str) and x.strip() for x in val):
                raise ModelRegistryError(f"{model_id}: spec.logic.{list_field} must be a non-empty list of strings")

        spec_sha = _sha256_bytes(spec_bytes)
        mod_sha = _sha256_bytes(module_bytes)
        combined_sha = _sha256_bytes(f"{spec_sha}:{mod_sha}".encode("ascii"))

        records.append(
            ModelRecord(
                model_id=model_id,
                category=category,
                display_name=display_name,
                version=version,
                evidence_status=evidence_status,
                drive_vault_folder_key=drive_folder_key,
                mql5_prefix=reg_prefix,
                magic_number=reg_magic,
                timeframe=timeframe,
                direction=direction,
                default_lot=default_lot,
                hedging_required=hedging_required,
                summary=summary.strip(),
                spec_path=spec_path,
                module_path=module_path,
                spec_sha256=spec_sha,
                module_sha256=mod_sha,
                combined_sha256=combined_sha,
            )
        )

    # Reject unregistered orphan spec.json files under models/{alpha,beta,omega}/
    models_root = registry_path.parent
    for cat in sorted(ALLOWED_CATEGORIES):
        cat_dir = models_root / cat
        if not cat_dir.is_dir():
            continue
        for spec_candidate in sorted(cat_dir.glob("*/spec.json")):
            if spec_candidate.resolve() not in registered_spec_paths:
                raise ModelRegistryError(
                    f"unregistered orphan model spec found: {spec_candidate.resolve().relative_to(root)}"
                )

    return ModelRegistry(
        repo_root=root,
        registry_path=registry_path,
        core_helpers_path=core_path,
        core_helpers_sha256=_sha256_bytes(core_bytes),
        categories=raw_categories,
        models=tuple(records),
    )


def load_portfolio_spec(portfolio_path: Path, registry: ModelRegistry) -> PortfolioSpec:
    """Load and validate a portfolio JSON manifest against a validated ModelRegistry."""
    if not portfolio_path.is_file():
        raise ModelRegistryError(f"portfolio manifest not found: {portfolio_path}")
    try:
        raw = json.loads(portfolio_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ModelRegistryError(f"invalid JSON in {portfolio_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ModelRegistryError("portfolio manifest root must be a JSON object")
    if raw.get("schema_version") != "1.0":
        raise ModelRegistryError(f"unsupported portfolio schema_version: {raw.get('schema_version')!r}")

    portfolio_id = raw.get("portfolio_id")
    if not isinstance(portfolio_id, str) or not _PORTFOLIO_ID_RE.fullmatch(portfolio_id):
        raise ModelRegistryError(f"invalid portfolio_id: {portfolio_id!r}")

    ea_name = raw.get("ea_name")
    if not isinstance(ea_name, str) or not _EA_NAME_RE.fullmatch(ea_name):
        raise ModelRegistryError(f"invalid ea_name: {ea_name!r}")

    description = raw.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ModelRegistryError("portfolio description must be a non-empty string")

    account_lock = _require_non_bool_int(raw.get("account_lock", 0), "account_lock", min_value=0)
    disable_interval = _require_non_bool_int(
        raw.get("disable_check_interval_seconds", 60),
        "disable_check_interval_seconds",
        min_value=1,
    )

    output_path = raw.get("output_path")
    if output_path is not None and (not isinstance(output_path, str) or not output_path.strip()):
        raise ModelRegistryError("output_path must be a non-empty relative string or null")

    raw_models = raw.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise ModelRegistryError("portfolio 'models' must be a non-empty list")

    seen: set[str] = set()
    slots: list[PortfolioSlot] = []
    for idx, item in enumerate(raw_models):
        if not isinstance(item, dict):
            raise ModelRegistryError(f"portfolio models[{idx}] must be an object")
        model_id = item.get("model_id")
        if not isinstance(model_id, str):
            raise ModelRegistryError(f"portfolio models[{idx}].model_id must be a string")
        if model_id in seen:
            raise ModelRegistryError(f"duplicate model_id {model_id!r} in portfolio {portfolio_id!r}")
        seen.add(model_id)
        record = registry.get(model_id)

        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ModelRegistryError(f"portfolio {model_id}.enabled must be a boolean")
        default_lot = _require_finite_float(
            item.get("default_lot", record.default_lot),
            f"portfolio {model_id}.default_lot",
            min_value=0.0,
        )
        slots.append(PortfolioSlot(model_id=model_id, enabled=enabled, default_lot=default_lot))

    return PortfolioSpec(
        portfolio_id=portfolio_id,
        ea_name=ea_name,
        description=description.strip(),
        account_lock=account_lock,
        disable_check_interval_seconds=disable_interval,
        output_path=output_path,
        slots=tuple(slots),
    )


def _format_mql5_double(val: float) -> str:
    formatted = f"{val:.4f}".rstrip("0")
    if formatted.endswith("."):
        formatted += "0"
    if "." in formatted and len(formatted.split(".")[1]) < 2:
        formatted = f"{val:.2f}"
    return formatted


def assemble_portfolio_mq5(registry: ModelRegistry, portfolio: PortfolioSpec) -> str:
    """Deterministically assemble a self-contained MT5 Hedging `.mq5` file from atomic modules."""
    core_code = registry.core_helpers_path.read_text(encoding="utf-8").strip()
    resolved_slots = [(slot, registry.get(slot.model_id)) for slot in portfolio.slots]

    header_models_lines: list[str] = []
    for idx, (_, rec) in enumerate(resolved_slots, start=1):
        header_models_lines.append(
            f"//|  {idx}) {rec.mql5_prefix:<10} [{rec.category}] v{rec.version}"
            f" | magic={rec.magic_number} | status={rec.evidence_status}"
            f" | sha={rec.combined_sha256[:12]}"
        )

    input_blocks: list[str] = [
        f"input long Account_Lock = {portfolio.account_lock}; // 0 = no account lock"
    ]
    for slot, rec in resolved_slots:
        bool_lit = "true" if slot.enabled else "false"
        lot_lit = _format_mql5_double(slot.default_lot)
        input_blocks.append(
            "\n".join(
                [
                    f"// {rec.model_id} — {rec.display_name}",
                    f"input bool   Enable_{rec.mql5_prefix} = {bool_lit};",
                    f"input double Lot_{rec.mql5_prefix}    = {lot_lit};",
                ]
            )
        )

    module_blocks: list[str] = []
    for _, rec in resolved_slots:
        mod_text = rec.module_path.read_text(encoding="utf-8").strip()
        module_blocks.append(mod_text)

    enforce_calls = "\n".join(
        f"   EnforceDisabled_{rec.mql5_prefix}(Enable_{rec.mql5_prefix}, Lot_{rec.mql5_prefix});"
        for _, rec in resolved_slots
    )

    lot_checks = " ||\n      ".join(
        f"Lot_{rec.mql5_prefix} < 0.0" for _, rec in resolved_slots
    )

    init_calls = "\n".join(f"   Init_{rec.mql5_prefix}();" for _, rec in resolved_slots)

    init_print_parts = "\n".join(
        f'      " | {rec.mql5_prefix}=", Enable_{rec.mql5_prefix},'
        for _, rec in resolved_slots
    ).rstrip(",")

    log_config_calls = "\n".join(f"   LogConfig_{rec.mql5_prefix}();" for _, rec in resolved_slots)

    process_calls = "\n".join(
        f"   Process_{rec.mql5_prefix}(Enable_{rec.mql5_prefix}, Lot_{rec.mql5_prefix});"
        for _, rec in resolved_slots
    )

    sections = [
        "\n".join(
            [
                "//+------------------------------------------------------------------+",
                f"//| {portfolio.ea_name}.mq5",
                "//| AUTO-GENERATED DETERMINISTICALLY BY scripts/build_ea_portfolio.py",
                f"//| Portfolio ID : {portfolio.portfolio_id}",
                f"//| Core Helpers : sha={registry.core_helpers_sha256[:12]}",
                "//| Account Mode : MT5 Hedging required",
                "//|",
                "//| Included Models (editable inputs: Enable & Lot only):",
                *header_models_lines,
                "//|",
                "//| DO NOT EDIT DIRECTLY — edit atomic files under models/ and rebuild.",
                "//+------------------------------------------------------------------+",
                "#property strict",
                "",
                "#include <Trade/Trade.mqh>",
                "",
                "CTrade trade;",
                f"datetime g_lastDisableCheck = 0;",
                f"#define DISABLE_CHECK_INTERVAL_SECONDS {portfolio.disable_check_interval_seconds}",
            ]
        ),
        "\n".join(
            [
                "//====================================================================//",
                "// USER INPUTS (Enable / Lot / Account_Lock ONLY)",
                "//====================================================================//",
                "",
                "\n\n".join(input_blocks),
            ]
        ),
        core_code,
        "\n\n\n".join(module_blocks),
        "\n".join(
            [
                "//====================================================================//",
                "// DISABLE CONTROL",
                "// false or 0 lot = no new entry and close that model's positions",
                "//====================================================================//",
                "",
                "void EnforceDisabledModels()",
                "{",
                "   datetime now = TimeCurrent();",
                "   if(g_lastDisableCheck > 0 &&",
                "      (now - g_lastDisableCheck) < DISABLE_CHECK_INTERVAL_SECONDS)",
                "      return;",
                "",
                "   g_lastDisableCheck = now;",
                "",
                enforce_calls,
                "}",
            ]
        ),
        "\n".join(
            [
                "//====================================================================//",
                "// INIT",
                "//====================================================================//",
                "",
                "int OnInit()",
                "{",
                "   long login = (long)AccountInfoInteger(ACCOUNT_LOGIN);",
                "",
                "   if(Account_Lock > 0 && login != Account_Lock)",
                "   {",
                '      Print("ACCOUNT LOCK FAILED | Allowed=", Account_Lock, " | Current=", login);',
                "      return INIT_FAILED;",
                "   }",
                "",
                "   if(!IsHedgingAccount())",
                "   {",
                '      Print("ERROR: This EA requires an MT5 HEDGING account.");',
                "      return INIT_FAILED;",
                "   }",
                "",
                f"   if({lot_checks})",
                "   {",
                '      Print("ERROR: Lot values must be >= 0.");',
                "      return INIT_PARAMETERS_INCORRECT;",
                "   }",
                "",
                "   trade.SetTypeFillingBySymbol(_Symbol);",
                "",
                init_calls,
                "",
                "   Print(",
                f'      "{portfolio.ea_name} initialized | Account=", login,',
                init_print_parts,
                "   );",
                "",
                log_config_calls,
                "",
                "   return INIT_SUCCEEDED;",
                "}",
            ]
        ),
        "\n".join(
            [
                "//====================================================================//",
                "// MAIN",
                "//====================================================================//",
                "",
                "void OnTick()",
                "{",
                "   EnforceDisabledModels();",
                "",
                "   // Independent per-model execution & bar clocks",
                process_calls,
                "}",
                "//+------------------------------------------------------------------+",
            ]
        ),
    ]

    assembled = "\n\n\n".join(sections) + "\n"
    _check_balanced_braces(assembled, f"assembled:{portfolio.portfolio_id}")
    return assembled


def assemble_single_model_mq5(
    registry: ModelRegistry,
    model_id: str,
    *,
    default_lot: float | None = None,
    account_lock: int = 0,
) -> str:
    """Assemble a standalone single-model `.mq5` EA directly from its atomic module."""
    record = registry.get(model_id)
    lot_val = record.default_lot if default_lot is None else _require_finite_float(default_lot, "default_lot", min_value=0.0)
    spec = PortfolioSpec(
        portfolio_id=f"standalone_{record.model_id}",
        ea_name=f"AlphaMining_{record.mql5_prefix}_Standalone",
        description=f"Standalone EA for atomic model {record.model_id} ({record.display_name}).",
        account_lock=_require_non_bool_int(account_lock, "account_lock", min_value=0),
        disable_check_interval_seconds=60,
        output_path=None,
        slots=(PortfolioSlot(model_id=record.model_id, enabled=True, default_lot=lot_val),),
    )
    return assemble_portfolio_mq5(registry, spec)
