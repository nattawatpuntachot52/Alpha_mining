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


def validate_workflow_text(name: str, text: str) -> list[str]:
    """Check GitHub Actions workflow text for forbidden secrets-in-if and hidden upload paths."""
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


if __name__ == "__main__":
    unittest.main()
