"""Static safety and artifact-upload invariant tests for .github/workflows/."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

_IF_KEY_RE = re.compile(r"^(\s*)(?:-\s*)?if\s*:(.*)$")
_SECRETS_REF_RE = re.compile(r"\bsecrets(?:\.[A-Za-z0-9_]+|\[\s*['\"][^'\"]+['\"]\s*\])")
_UPLOAD_USES_RE = re.compile(r"^(\s*)(?:-\s*)?uses\s*:\s*['\"]?actions/upload-artifact@")
_GH_PR_CMD_RE = re.compile(r"\bgh\s+pr\s+(view|list)\b([^\n;|&)]*)")
_GH_JSON_ARG_RE = re.compile(r"(?:^|\s)--json(?:=|\s+)([^\s'\"`|;&)]+|'[^']*'|\"[^\"]*\")")
_RCLONE_BACKEND_RE = re.compile(r"(?:^|\s)--backend(?:=|\s+)['\"]?rclone['\"]?(?:\s|$|[;|&)])")
_RCLONE_INSTALL_RE = re.compile(
    r"(?:^|[;&|]\s*|&&\s*)(?!echo\b|printf\b)(?:sudo\s+)?"
    r"(?:(?:[A-Z_][A-Z0-9_]*=\S+\s+)*(?:apt-get|apt|dnf|yum|apk|snap|brew)\s+[^\n;|&]*?\binstall\b[^\n;|&]*?\brclone\b"
    r"|(?:curl|wget)\b[^\n;|&]*rclone\.org/install\.sh)"
)
_RCLONE_USES_RE = re.compile(r"(?:^|/)[^/\s]*rclone[^/\s]*@")

VALID_GH_PR_JSON_FIELDS = frozenset(
    {
        "additions",
        "assignees",
        "author",
        "autoMergeRequest",
        "baseRefName",
        "baseRefOid",
        "body",
        "changedFiles",
        "closed",
        "closedAt",
        "closingIssuesReferences",
        "comments",
        "commits",
        "createdAt",
        "deletions",
        "files",
        "fullDatabaseId",
        "headRefName",
        "headRefOid",
        "headRepository",
        "headRepositoryOwner",
        "id",
        "isCrossRepository",
        "isDraft",
        "labels",
        "latestReviews",
        "maintainerCanModify",
        "mergeCommit",
        "mergeStateStatus",
        "mergeable",
        "mergedAt",
        "mergedBy",
        "milestone",
        "number",
        "potentialMergeCommit",
        "projectCards",
        "projectItems",
        "reactionGroups",
        "reviewDecision",
        "reviewRequests",
        "reviews",
        "state",
        "statusCheckRollup",
        "title",
        "updatedAt",
        "url",
    }
)


def _strip_inline_comment(line: str) -> str:
    in_single = False
    in_double = False
    for idx, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if idx == 0 or line[idx - 1].isspace():
                return line[:idx]
    return line


def _has_hidden_segment(path_spec: str) -> bool:
    for raw_line in path_spec.splitlines():
        token = raw_line.strip().strip("'\"")
        if not token or token.startswith("!"):
            continue
        normalized = token.replace("\\", "/")
        parts = [p for p in normalized.split("/") if p]
        for part in parts:
            if part in {".", ".."}:
                continue
            if part.startswith("."):
                return True
    return False


def _validate_gh_pr_json_invocations(name: str, lines: list[str]) -> list[str]:
    """Validate `--json` fields passed to `gh pr view` / `gh pr list` across single and `\\`-continued lines."""
    errors: list[str] = []
    idx = 0
    while idx < len(lines):
        raw = lines[idx]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            idx += 1
            continue

        start_line = idx + 1
        combined = _strip_inline_comment(raw).rstrip()
        j = idx
        while combined.endswith("\\") and j + 1 < len(lines):
            combined = combined[:-1].rstrip() + " " + _strip_inline_comment(lines[j + 1]).strip()
            j += 1

        for cmd_match in _GH_PR_CMD_RE.finditer(combined):
            subcmd = cmd_match.group(1)
            args_tail = cmd_match.group(2)
            for arg_match in _GH_JSON_ARG_RE.finditer(args_tail):
                raw_val = arg_match.group(1).strip("'\"")
                if "$" in raw_val:
                    continue
                fields = [part.strip() for part in raw_val.split(",")]
                if not fields or any(not field for field in fields):
                    errors.append(
                        f"{name}:{start_line}: empty field in `gh pr {subcmd} --json {raw_val}`"
                    )
                    continue
                unknown = [field for field in fields if field not in VALID_GH_PR_JSON_FIELDS]
                if unknown:
                    errors.append(
                        f"{name}:{start_line}: unknown `gh pr {subcmd} --json` field(s): {', '.join(unknown)}"
                    )

        idx = j + 1
    return errors


def _validate_rclone_install_before_use(name: str, lines: list[str]) -> list[str]:
    """Ensure Ubuntu jobs invoking `--backend rclone` install `rclone` before calling it."""
    errors: list[str] = []
    in_jobs = False
    jobs_indent = -1
    job_indent: int | None = None
    block_indent: int | None = None
    in_run_block = False
    current_job: str | None = None
    runs_on_ubuntu = False
    rclone_installed = False

    idx = 0
    while idx < len(lines):
        raw = lines[idx]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            idx += 1
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        if block_indent is not None:
            if indent <= block_indent:
                block_indent = None
                in_run_block = False
            else:
                if current_job is not None and in_run_block:
                    start_line = idx + 1
                    combined = _strip_inline_comment(raw).rstrip()
                    j = idx
                    while combined.endswith("\\") and j + 1 < len(lines):
                        combined = combined[:-1].rstrip() + " " + _strip_inline_comment(lines[j + 1]).strip()
                        j += 1
                    cmd_text = combined.strip()
                    if not cmd_text.startswith(("echo ", "printf ")):
                        install_match = _RCLONE_INSTALL_RE.search(cmd_text)
                        backend_match = _RCLONE_BACKEND_RE.search(cmd_text)
                        if backend_match and runs_on_ubuntu:
                            installed_here_first = (
                                install_match is not None and install_match.start() < backend_match.start()
                            )
                            if not (rclone_installed or installed_here_first):
                                errors.append(
                                    f"{name}:{start_line}: job '{current_job}' invokes `--backend rclone` "
                                    "on ubuntu runner without installing `rclone` beforehand"
                                )
                        if install_match:
                            rclone_installed = True
                    idx = j + 1
                    continue
                idx += 1
                continue

        clean = _strip_inline_comment(raw).strip()
        if not clean:
            idx += 1
            continue

        if re.match(r"^jobs\s*:$", clean):
            in_jobs = True
            jobs_indent = indent
            job_indent = None
            current_job = None
            runs_on_ubuntu = False
            rclone_installed = False
            idx += 1
            continue

        if in_jobs and indent <= jobs_indent:
            in_jobs = False
            current_job = None

        if in_jobs:
            job_match = re.match(r"^([A-Za-z0-9_-]+)\s*:(.*)$", clean)
            if (
                job_match
                and not raw.lstrip().startswith("-")
                and (job_indent is None or indent == job_indent)
                and indent > jobs_indent
            ):
                job_indent = indent
                current_job = job_match.group(1)
                runs_on_ubuntu = False
                rclone_installed = False
                idx += 1
                continue

            if current_job is not None:
                runs_on_match = re.match(r"^(?:-\s*)?runs-on\s*:\s*(.+)$", clean)
                if runs_on_match and "ubuntu" in runs_on_match.group(1).lower():
                    runs_on_ubuntu = True
                uses_match = re.match(r"^(?:-\s*)?uses\s*:\s*([^\s#]+)", clean)
                if uses_match and _RCLONE_USES_RE.search(uses_match.group(1).strip("'\"")):
                    rclone_installed = True

                run_key_match = re.match(r"^(?:-\s*)?run\s*:\s*(.*)$", clean)
                key_offset = 2 if raw.lstrip().startswith("-") else 0
                if run_key_match:
                    rhs = run_key_match.group(1).strip()
                    if rhs in {"|", "|-", "|+", ">", ">-", ">+"}:
                        block_indent = indent + key_offset
                        in_run_block = True
                    else:
                        install_match = _RCLONE_INSTALL_RE.search(rhs)
                        backend_match = _RCLONE_BACKEND_RE.search(rhs)
                        if backend_match and runs_on_ubuntu and not rhs.startswith(("echo ", "printf ")):
                            installed_here_first = (
                                install_match is not None and install_match.start() < backend_match.start()
                            )
                            if not (rclone_installed or installed_here_first):
                                errors.append(
                                    f"{name}:{idx + 1}: job '{current_job}' invokes `--backend rclone` "
                                    "on ubuntu runner without installing `rclone` beforehand"
                                )
                        if install_match and not rhs.startswith(("echo ", "printf ")):
                            rclone_installed = True
                elif clean.endswith(("|", "|-", "|+", ">", ">-", ">+")):
                    block_indent = indent + key_offset
                    in_run_block = False

        idx += 1

    return errors


def validate_workflow_text(name: str, text: str) -> list[str]:
    """Check GitHub Actions workflow text for secrets-in-if, hidden paths, gh pr --json, and rclone install."""
    errors: list[str] = []
    lines = text.splitlines()
    idx = 0

    while idx < len(lines):
        raw = lines[idx]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            idx += 1
            continue

        # 1. Forbid `secrets.*` inside any `if:` expression (including multiline `if: |` / `>`).
        if_match = _IF_KEY_RE.match(raw)
        if if_match:
            key_indent = len(if_match.group(1)) + (2 if raw.lstrip().startswith("-") else 0)
            rhs = _strip_inline_comment(if_match.group(2)).strip()
            if _SECRETS_REF_RE.search(rhs):
                errors.append(f"{name}:{idx + 1}: `secrets` context is forbidden inside `if:` expressions")
            if rhs in {"|", "|-", "|+", ">", ">-", ">+"}:
                j = idx + 1
                while j < len(lines):
                    nxt = lines[j]
                    nxt_strip = nxt.strip()
                    if not nxt_strip:
                        j += 1
                        continue
                    nxt_indent = len(nxt) - len(nxt.lstrip(" "))
                    if nxt_indent <= key_indent:
                        break
                    if _SECRETS_REF_RE.search(nxt_strip):
                        errors.append(
                            f"{name}:{j + 1}: `secrets` context is forbidden inside multiline `if:` expressions"
                        )
                    j += 1
                idx = j
                continue

        # 2. Require `include-hidden-files: true` whenever `actions/upload-artifact` uploads a hidden path.
        uses_match = _UPLOAD_USES_RE.match(raw)
        if uses_match:
            step_indent = len(uses_match.group(1))
            if raw.lstrip().startswith("-"):
                step_indent += 2
            step_lines: list[str] = []
            j = idx + 1
            while j < len(lines):
                nxt = lines[j]
                nxt_strip = nxt.strip()
                if not nxt_strip or nxt_strip.startswith("#"):
                    j += 1
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip(" "))
                if nxt_indent < step_indent or (nxt_indent == step_indent and nxt_strip.startswith("-")):
                    break
                step_lines.append(nxt)
                j += 1

            path_values: list[str] = []
            include_hidden = False
            s_idx = 0
            while s_idx < len(step_lines):
                s_raw = step_lines[s_idx]
                s_clean = _strip_inline_comment(s_raw).strip()
                if s_clean.startswith("path:"):
                    p_indent = len(s_raw) - len(s_raw.lstrip(" "))
                    p_rhs = s_clean[len("path:") :].strip()
                    if p_rhs in {"|", "|-", "|+", ">", ">-", ">+"}:
                        k = s_idx + 1
                        block: list[str] = []
                        while k < len(step_lines):
                            b_raw = step_lines[k]
                            if not b_raw.strip():
                                k += 1
                                continue
                            b_indent = len(b_raw) - len(b_raw.lstrip(" "))
                            if b_indent <= p_indent:
                                break
                            block.append(_strip_inline_comment(b_raw))
                            k += 1
                        path_values.append("\n".join(block))
                        s_idx = k
                        continue
                    path_values.append(p_rhs)
                elif s_clean.startswith("include-hidden-files:"):
                    flag = s_clean[len("include-hidden-files:") :].strip().strip("'\"").lower()
                    include_hidden = flag == "true"
                s_idx += 1

            if any(_has_hidden_segment(p) for p in path_values) and not include_hidden:
                errors.append(
                    f"{name}:{idx + 1}: actions/upload-artifact uploads dot-prefixed path "
                    f"{path_values!r} without `include-hidden-files: true`"
                )

        idx += 1

    # 3. Validate `gh pr view` / `gh pr list` `--json` fields against documented gh CLI fields.
    errors.extend(_validate_gh_pr_json_invocations(name, lines))

    # 4. Require installing `rclone` before invoking `--backend rclone` on Ubuntu runners.
    errors.extend(_validate_rclone_install_before_use(name, lines))

    return errors


class TestGitHubWorkflows(unittest.TestCase):
    def test_all_repo_workflows_pass_static_safety_and_artifact_invariants(self) -> None:
        workflow_files = sorted(list(WORKFLOWS_DIR.glob("*.yml")) + list(WORKFLOWS_DIR.glob("*.yaml")))
        self.assertGreaterEqual(len(workflow_files), 4)
        all_errors: list[str] = []
        for wf in workflow_files:
            all_errors.extend(validate_workflow_text(wf.name, wf.read_text(encoding="utf-8")))
        self.assertEqual(all_errors, [], "\n".join(all_errors))

    def test_ovca_reviewer_bot_checks_private_key_via_env_not_if(self) -> None:
        text = (WORKFLOWS_DIR / "ovca-reviewer-bot.yml").read_text(encoding="utf-8")
        self.assertIn("OVCA_APP_PRIVATE_KEY: ${{ secrets.OVCA_REVIEWER_APP_PRIVATE_KEY }}", text)
        self.assertNotIn("if: ${{ secrets.", text)

    def test_ovca_reviewer_bot_uses_valid_same_repo_pr_meta_fields(self) -> None:
        text = (WORKFLOWS_DIR / "ovca-reviewer-bot.yml").read_text(encoding="utf-8")
        self.assertNotIn("baseRepository", text)
        self.assertIn("--json state,isDraft,headRefOid,isCrossRepository,headRepository", text)
        self.assertIn('d.get("isCrossRepository") is False', text)
        self.assertIn('"nameWithOwner"', text)

    def test_admission_observe_uploads_hidden_observe_out_with_flag(self) -> None:
        text = (WORKFLOWS_DIR / "admission-observe.yml").read_text(encoding="utf-8")
        self.assertIn("path: .observe_out/", text)
        self.assertIn("include-hidden-files: true", text)

    def test_validator_rejects_secrets_in_if_and_missing_hidden_flag_only_for_hidden_paths(self) -> None:
        bad_if = """
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - name: Bad
        if: ${{ secrets.MY_KEY == '' }}
        run: echo hi
"""
        self.assertTrue(validate_workflow_text("bad-if.yml", bad_if))

        bad_multiline_if = """
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - name: Bad multiline
        if: |
          secrets.MY_KEY != ''
        run: echo hi
"""
        self.assertTrue(validate_workflow_text("bad-multi.yml", bad_multiline_if))

        bad_upload = """
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/upload-artifact@v4
        with:
          name: report
          path: .observe_out/
"""
        self.assertTrue(validate_workflow_text("bad-upload.yml", bad_upload))

        bad_bracket_after_uses = """
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/upload-artifact@v4
        if: ${{ secrets['BAD_KEY'] != '' }}
        with:
          name: report
          path: out/.hidden
          include-hidden-files: false
"""
        bracket_errs = validate_workflow_text("bad-bracket.yml", bad_bracket_after_uses)
        self.assertEqual(len(bracket_errs), 2, bracket_errs)

        ok_rel_upload = """
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/upload-artifact@v4
        with:
          name: report
          path: ./observe_out/
"""
        self.assertEqual(validate_workflow_text("ok-rel.yml", ok_rel_upload), [])

    def test_validator_rejects_unknown_gh_pr_json_fields(self) -> None:
        bad_pr_view = """
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - run: |
          PR_META=$(gh pr view "$PR" -R "$REPO" --json state,headRepository,baseRepository)
"""
        errs = validate_workflow_text("bad-pr-view.yml", bad_pr_view)
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("baseRepository", errs[0])

        bad_pr_list_multiline = """
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - run: |
          gh pr list -R "$REPO" \\
            --state open \\
            --json=number,nonExistentField
"""
        list_errs = validate_workflow_text("bad-pr-list.yml", bad_pr_list_multiline)
        self.assertEqual(len(list_errs), 1, list_errs)
        self.assertIn("nonExistentField", list_errs[0])

        ok_pr_view_and_json_out = """
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - run: |
          gh pr view 4 -R "$REPO" --json state,isDraft,headRefOid,isCrossRepository,headRepository
          python3 scripts/admission_gate.py observe --json-out .observe_out/report.json
"""
        self.assertEqual(validate_workflow_text("ok-pr-view.yml", ok_pr_view_and_json_out), [])

    def test_vault_sync_ensures_rclone_installed_before_pull_drive(self) -> None:
        text = (WORKFLOWS_DIR / "vault-sync.yml").read_text(encoding="utf-8")
        secret_guard_pos = text.find("RCLONE_CONFIG_GDRIVE secret is not set")
        install_guard_pos = text.find("if ! command -v rclone")
        apt_install_pos = text.find("apt-get install -y -qq --no-install-recommends rclone")
        gdrive_check_pos = text.find("[gdrive]")
        pull_pos = text.find('RCLONE_CONFIG="$RCLONE_TMP" python3 scripts/vault_sync.py pull-drive')
        self.assertGreater(secret_guard_pos, 0)
        self.assertGreater(install_guard_pos, secret_guard_pos)
        self.assertGreater(apt_install_pos, install_guard_pos)
        self.assertGreater(gdrive_check_pos, apt_install_pos)
        self.assertGreater(pull_pos, gdrive_check_pos)
        self.assertIn("--backend rclone", text[pull_pos:])
        self.assertIn("tr -d '\\r'", text)
        self.assertNotIn("rclone --version | head", text)

    def test_validator_rejects_rclone_backend_without_prior_install(self) -> None:
        bad_no_install = """
jobs:
  vault:
    runs-on: ubuntu-latest
    steps:
      - run: |
          python3 scripts/vault_sync.py pull-drive \\
            --manifest m.json \\
            --dest .vault_staging \\
            --backend rclone
"""
        errs = validate_workflow_text("bad-no-rclone.yml", bad_no_install)
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("--backend rclone", errs[0])

        bad_echo_only = """
jobs:
  vault:
    runs-on: ubuntu-latest
    steps:
      - run: |
          echo "apt-get install -y rclone"
          python3 scripts/vault_sync.py pull-drive --backend rclone
"""
        self.assertEqual(len(validate_workflow_text("bad-echo-rclone.yml", bad_echo_only)), 1)

        bad_after_use = """
jobs:
  vault:
    runs-on: ubuntu-latest
    steps:
      - run: |
          python3 scripts/vault_sync.py pull-drive --backend rclone
          sudo apt-get install -y rclone
"""
        self.assertEqual(len(validate_workflow_text("bad-order-rclone.yml", bad_after_use)), 1)

        bad_other_job = """
jobs:
  prep:
    runs-on: ubuntu-latest
    steps:
      - run: sudo apt-get install -y rclone
  vault:
    runs-on: ubuntu-latest
    steps:
      - run: python3 scripts/vault_sync.py pull-drive --backend rclone
"""
        job_errs = validate_workflow_text("bad-other-job.yml", bad_other_job)
        self.assertEqual(len(job_errs), 1, job_errs)
        self.assertIn("vault", job_errs[0])

        ok_apt_before = """
jobs:
  vault:
    runs-on: ubuntu-latest
    steps:
      - run: |
          if ! command -v rclone >/dev/null 2>&1; then
            sudo apt-get update -qq
            sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends rclone
          fi
          python3 scripts/vault_sync.py pull-drive --backend rclone
"""
        self.assertEqual(validate_workflow_text("ok-apt-rclone.yml", ok_apt_before), [])

        ok_action_before = """
jobs:
  vault:
    runs-on: ubuntu-24.04
    steps:
      - uses: NiceLabs/setup-rclone@v1
      - run: python3 scripts/vault_sync.py pull-drive --backend=rclone
"""
        self.assertEqual(validate_workflow_text("ok-action-rclone.yml", ok_action_before), [])


if __name__ == "__main__":
    unittest.main()
