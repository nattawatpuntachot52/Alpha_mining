"""Bridge between Python Quant workflows and the deterministic Rust alpha-ovca CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ClaimKind = Literal[
    "fact",
    "assumption",
    "hypothesis",
    "inference",
    "computed_result",
    "independently_verified_result",
]

EvidenceStatus = Literal[
    "proposed",
    "exploratory",
    "reproducible",
    "robustness_validated",
    "independently_replicated",
]


class OvcaBridgeError(RuntimeError):
    """Raised when the alpha-ovca binary rejects a brief or workflow event stream."""


def utc_now_z() -> str:
    """Return an ISO-8601 UTC timestamp ending in Z as required by OVCA v1.0."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class EpistemicClaim:
    """Structured claim enforcing honest separation of facts, hypotheses, and verified results."""

    kind: ClaimKind
    statement: str
    evidence_status: EvidenceStatus
    source_ref: str

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("claim.statement must not be empty")
        if not self.source_ref.strip():
            raise ValueError("claim.source_ref must not be empty")
        if self.evidence_status in (
            "robustness_validated",
            "independently_replicated",
        ) and self.kind not in ("fact", "independently_verified_result"):
            raise ValueError(
                "robustness_validated or independently_replicated status requires "
                "kind 'fact' or 'independently_verified_result'"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "statement": self.statement,
            "evidence_status": self.evidence_status,
            "source_ref": self.source_ref,
        }


def default_repo_root() -> Path:
    """Resolve the Alpha_mining repository root from this module's path."""
    return Path(__file__).resolve().parents[3]


class OvcaBridge:
    """Executes deterministic OVCA v1.0 validation via the Rust `alpha-ovca` binary."""

    def __init__(
        self,
        repo_root: Path | str | None = None,
        binary_path: Path | str | None = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root else default_repo_root()
        self.manifest_path = self.repo_root / "rust" / "Cargo.toml"
        self._explicit_binary = Path(binary_path) if binary_path else None

    def _latest_rust_input_mtime(self) -> float:
        latest = 0.0
        for path in (
            self.manifest_path,
            self.repo_root / "rust" / "Cargo.lock",
        ):
            if path.is_file():
                latest = max(latest, path.stat().st_mtime)
        crates_dir = self.repo_root / "rust" / "crates"
        if crates_dir.is_dir():
            for pattern in ("*.rs", "Cargo.toml"):
                for p in crates_dir.rglob(pattern):
                    if p.is_file():
                        latest = max(latest, p.stat().st_mtime)
        return latest

    def resolve_binary(self) -> Path:
        """Locate an up-to-date `alpha-ovca` binary or build deterministically with `--locked`."""
        if self._explicit_binary is not None:
            if not self._explicit_binary.is_file():
                raise OvcaBridgeError(
                    f"explicit alpha-ovca binary not found: {self._explicit_binary}"
                )
            return self._explicit_binary

        if self.manifest_path.is_file():
            latest_input_mtime = self._latest_rust_input_mtime()
            for candidate in (
                self.repo_root / "rust" / "target" / "release" / "alpha-ovca",
                self.repo_root / "rust" / "target" / "debug" / "alpha-ovca",
            ):
                if candidate.is_file() and candidate.stat().st_mtime >= latest_input_mtime:
                    return candidate

            try:
                build_proc = subprocess.run(
                    [
                        "cargo",
                        "build",
                        "--manifest-path",
                        str(self.manifest_path),
                        "--bin",
                        "alpha-ovca",
                        "--locked",
                    ],
                    cwd=str(self.repo_root),
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise OvcaBridgeError(
                    "cargo executable not found on PATH while building alpha-ovca"
                ) from exc
            if build_proc.returncode != 0:
                raise OvcaBridgeError(
                    f"failed to build alpha-ovca: {build_proc.stderr.strip()}"
                )

            built = self.repo_root / "rust" / "target" / "debug" / "alpha-ovca"
            if not built.is_file():
                raise OvcaBridgeError(f"built binary missing at expected path: {built}")
            return built

        which_bin = shutil.which("alpha-ovca")
        if which_bin:
            return Path(which_bin)
        raise OvcaBridgeError(
            f"alpha-ovca binary not found and Cargo manifest missing: {self.manifest_path}"
        )

    def _run(self, args: list[str]) -> dict[str, Any]:
        binary = self.resolve_binary()
        proc = subprocess.run(
            [str(binary), *args],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip()
            raise OvcaBridgeError(detail)
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise OvcaBridgeError(
                f"alpha-ovca returned non-JSON output: {proc.stdout!r}"
            ) from exc

    def validate_brief(self, brief_path: Path | str) -> dict[str, Any]:
        return self._run(["validate-brief", str(brief_path)])

    def init_workflow(
        self,
        brief_path: Path | str,
        workflow_id: str,
        event_id: str,
        occurred_at: str,
        out_path: Path | str,
    ) -> dict[str, Any]:
        return self._run(
            [
                "init-workflow",
                "--brief",
                str(brief_path),
                "--workflow-id",
                workflow_id,
                "--event-id",
                event_id,
                "--occurred-at",
                occurred_at,
                "--out",
                str(out_path),
            ]
        )

    def verify_stream(
        self,
        stream_path: Path | str,
        brief_path: Path | str | None = None,
    ) -> dict[str, Any]:
        args = ["verify-stream", str(stream_path)]
        if brief_path is not None:
            args.extend(["--brief", str(brief_path)])
        return self._run(args)

    def status(
        self,
        stream_path: Path | str,
        brief_path: Path | str | None = None,
    ) -> dict[str, Any]:
        args = ["status", str(stream_path)]
        if brief_path is not None:
            args.extend(["--brief", str(brief_path)])
        return self._run(args)

    def append_event(
        self,
        stream_path: Path | str,
        event_path: Path | str,
        brief_path: Path | str | None = None,
    ) -> dict[str, Any]:
        args = ["append-event", "--stream", str(stream_path), "--event", str(event_path)]
        if brief_path is not None:
            args.extend(["--brief", str(brief_path)])
        return self._run(args)

    def policy_version(self, policy_path: Path | str) -> dict[str, Any]:
        return self._run(["policy-version", str(policy_path)])

    def validate_mandate(
        self,
        mandate_path: Path | str,
        *,
        brief_path: Path | str | None = None,
        policy_path: Path | str | None = None,
    ) -> dict[str, Any]:
        args = ["validate-mandate", str(mandate_path)]
        if brief_path is not None:
            args.extend(["--brief", str(brief_path)])
        if policy_path is not None:
            args.extend(["--policy", str(policy_path)])
        return self._run(args)

    def revalidate_mandate(
        self,
        mandate_path: Path | str,
        policy_path: Path | str,
    ) -> dict[str, Any]:
        return self._run(
            [
                "revalidate-mandate",
                "--mandate",
                str(mandate_path),
                "--policy",
                str(policy_path),
            ]
        )

    def check_followup(
        self,
        mandate_path: Path | str,
        followup_path: Path | str,
        policy_path: Path | str,
    ) -> dict[str, Any]:
        return self._run(
            [
                "check-followup",
                "--mandate",
                str(mandate_path),
                "--followup",
                str(followup_path),
                "--policy",
                str(policy_path),
            ]
        )
