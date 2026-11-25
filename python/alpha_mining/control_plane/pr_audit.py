"""Multi-PR Semantic Conflict & Pre-Merge Readiness Audit for Alpha_mining."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .agent_ack import AgentAckReport, validate_agent_ack


class PrAuditError(RuntimeError):
    """Raised when PR audit inputs cannot be loaded or inspected."""


CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]

CONTRACT_CRITICAL_PREFIXES = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "roles/",
    "config/",
    "workflows/templates/",
    "rust/crates/alpha-ovca/src/",
    "pyproject.toml",
    ".github/workflows/",
)

ISOLATED_FACTORY_DATA_PREFIXES = (
    "alpha_mining/",
    "beta_mining/",
)

_FAIL_CONCLUSIONS = frozenset(
    {
        "FAILURE",
        "ERROR",
        "TIMED_OUT",
        "CANCELLED",
        "ACTION_REQUIRED",
        "STARTUP_FAILURE",
        "STALE",
    }
)
_PASS_CONCLUSIONS = frozenset({"SUCCESS", "NEUTRAL", "SKIPPED"})
_TRUSTED_BOT_ACTORS = frozenset({"ovca-reviewer[bot]", "alpha-mining-ovca-reviewer[bot]", "github-actions[bot]"})


def _default_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _is_contract_file(path: str) -> bool:
    if path.endswith(".schema.json") or "schema" in Path(path).name.lower():
        return True
    return any(path == prefix or path.startswith(prefix) for prefix in CONTRACT_CRITICAL_PREFIXES)


def _isolated_factory_domain(files: tuple[str, ...]) -> str | None:
    """Return the factory prefix if all PR files stay strictly inside one non-contract data factory directory."""
    if not files:
        return None
    for prefix in ISOLATED_FACTORY_DATA_PREFIXES:
        if all(f.startswith(prefix) and not _is_contract_file(f) for f in files):
            return prefix
    return None


def _normalize_stem(segment: str) -> str:
    """Normalize singular/plural and kebab/snake tokens for sibling collision detection."""
    stem = segment.rsplit(".", 1)[0] if "." in segment else segment
    norm = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
    if len(norm) > 3 and norm.endswith("s") and not norm.endswith("ss"):
        norm = norm[:-1]
    return norm


def _path_parts(path: str) -> list[str]:
    return [p for p in path.strip("/").split("/") if p]


def _directory_sibling_pairs(files_a: list[str], files_b: list[str]) -> list[tuple[str, str]]:
    """Detect semantic sibling naming collisions (e.g. mission.json vs missions/m1.json, context_manifests vs context-manifests)."""
    collisions: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for pa in files_a:
        parts_a = _path_parts(pa)
        for pb in files_b:
            if pa == pb:
                continue
            parts_b = _path_parts(pb)
            max_depth = min(len(parts_a), len(parts_b))
            for idx in range(max_depth):
                if parts_a[:idx] != parts_b[:idx]:
                    break
                seg_a = parts_a[idx]
                seg_b = parts_b[idx]
                if seg_a == seg_b:
                    continue
                if _normalize_stem(seg_a) == _normalize_stem(seg_b) and _normalize_stem(seg_a) != "":
                    pair = (pa, pb)
                    if pair not in seen:
                        seen.add(pair)
                        collisions.append(pair)
                    break
    return collisions


def _escape_md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


@dataclass(frozen=True)
class PrCommentRecord:
    body: str
    author: str | None = None


@dataclass(frozen=True)
class AuditFinding:
    code: str
    severity: str  # "critical" | "warning" | "info"
    message: str
    related_prs: tuple[int, ...] = ()


@dataclass(frozen=True)
class PullRequestSnapshot:
    number: int
    title: str
    author: str
    base_ref_name: str
    head_ref_name: str
    base_ref_oid: str
    head_ref_oid: str
    is_draft: bool
    state: str
    mergeable: str  # MERGEABLE | CONFLICTING | UNKNOWN
    merge_state_status: str  # CLEAN | BLOCKED | DIRTY | BEHIND | UNSTABLE | UNKNOWN
    body: str
    comments: tuple[PrCommentRecord, ...]
    files: tuple[str, ...]
    checks_summary: str  # SUCCESS | FAILURE | PENDING | NONE
    review_count: int
    unresolved_threads: int
    is_cross_repository: bool = False
    url: str = ""


@dataclass(frozen=True)
class PullRequestAuditResult:
    pr: PullRequestSnapshot
    agent_ack: AgentAckReport
    verdict: str
    findings: tuple[AuditFinding, ...] = field(default_factory=tuple)


def _summarize_checks(rollup: list[dict[str, Any]]) -> str:
    if not rollup:
        return "NONE"
    outcomes: list[str] = []
    pending_seen = False
    for item in rollup:
        if not isinstance(item, dict):
            continue
        concl = str(item.get("conclusion") or "").upper()
        status = str(item.get("status") or "").upper()
        state = str(item.get("state") or "").upper()  # Legacy StatusContext items
        if concl:
            outcomes.append(concl)
        elif status:
            if status != "COMPLETED":
                pending_seen = True
        elif state:
            if state in ("PENDING", "EXPECTED"):
                pending_seen = True
            else:
                outcomes.append(state)

    if any(o in _FAIL_CONCLUSIONS for o in outcomes):
        return "FAILURE"
    if pending_seen:
        return "PENDING"
    if outcomes and all(o in _PASS_CONCLUSIONS for o in outcomes):
        return "SUCCESS"
    return "PENDING"


def parse_pr_snapshots(raw_prs: list[dict[str, Any]]) -> list[PullRequestSnapshot]:
    snapshots: list[PullRequestSnapshot] = []
    for raw in raw_prs:
        author_obj = raw.get("author") or {}
        author = author_obj.get("login", str(author_obj)) if isinstance(author_obj, dict) else str(author_obj)
        files = tuple(
            f.get("path", f) if isinstance(f, dict) else str(f)
            for f in (raw.get("files") or [])
        )
        comments_list: list[PrCommentRecord] = []
        for c in raw.get("comments") or []:
            if isinstance(c, dict):
                c_author_obj = c.get("author")
                c_author = (
                    c_author_obj.get("login")
                    if isinstance(c_author_obj, dict)
                    else (str(c_author_obj) if c_author_obj else None)
                )
                comments_list.append(PrCommentRecord(body=str(c.get("body", "")), author=c_author))
            else:
                comments_list.append(PrCommentRecord(body=str(c), author=None))

        checks_raw = raw.get("statusCheckRollup") or raw.get("checks") or []
        if isinstance(checks_raw, str):
            checks_summary = checks_raw.upper()
        else:
            checks_summary = _summarize_checks(checks_raw)

        reviews = raw.get("reviews")
        review_count = raw.get("review_count")
        if review_count is None:
            review_count = len(reviews) if isinstance(reviews, list) else 0

        snapshots.append(
            PullRequestSnapshot(
                number=int(raw["number"]),
                title=str(raw.get("title", "")),
                author=author,
                base_ref_name=str(raw.get("baseRefName", "main")),
                head_ref_name=str(raw.get("headRefName", "")),
                base_ref_oid=str(raw.get("baseRefOid", "")),
                head_ref_oid=str(raw.get("headRefOid", "")),
                is_draft=bool(raw.get("isDraft", False)),
                state=str(raw.get("state", "OPEN")).upper(),
                mergeable=str(raw.get("mergeable", "UNKNOWN")).upper(),
                merge_state_status=str(raw.get("mergeStateStatus", "UNKNOWN")).upper(),
                body=str(raw.get("body", "")),
                comments=tuple(comments_list),
                files=files,
                checks_summary=checks_summary,
                review_count=int(review_count),
                unresolved_threads=int(raw.get("unresolved_threads", 0)),
                is_cross_repository=bool(raw.get("isCrossRepository", False)),
                url=str(raw.get("url", "")),
            )
        )
    return sorted(snapshots, key=lambda item: item.number)


def _fetch_unresolved_threads_map(
    repo: str,
    runner: CommandRunner = _default_runner,
) -> dict[int, int]:
    """Paginated GraphQL query for unresolved review thread counts per open PR."""
    if "/" not in repo:
        return {}
    owner, name = repo.split("/", 1)
    query = (
        "query($owner: String!, $name: String!, $cursor: String) { "
        "repository(owner: $owner, name: $name) { "
        "pullRequests(states: OPEN, first: 50, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) { "
        "pageInfo { hasNextPage endCursor } "
        "nodes { number reviewThreads(first: 100) { nodes { isResolved } } } "
        "} } }"
    )
    counts: dict[int, int] = {}
    cursor: str | None = None
    while True:
        cmd = [
            "gh",
            "api",
            "graphql",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-f",
            f"query={query}",
        ]
        if cursor:
            cmd.extend(["-F", f"cursor={cursor}"])
        proc = runner(cmd)
        if proc.returncode != 0 or not proc.stdout.strip():
            break
        try:
            data = json.loads(proc.stdout)
            pr_conn = data.get("data", {}).get("repository", {}).get("pullRequests", {})
            nodes = pr_conn.get("nodes", [])
            page_info = pr_conn.get("pageInfo") or {}
        except (json.JSONDecodeError, AttributeError):
            break

        for node in nodes:
            if not isinstance(node, dict) or "number" not in node:
                continue
            threads = (node.get("reviewThreads") or {}).get("nodes") or []
            counts[int(node["number"])] = sum(
                1 for t in threads if isinstance(t, dict) and not t.get("isResolved", False)
            )

        if not page_info.get("hasNextPage") or not page_info.get("endCursor"):
            break
        cursor = str(page_info["endCursor"])
    return counts


def fetch_open_prs(repo: str, runner: CommandRunner = _default_runner) -> list[PullRequestSnapshot]:
    """Fetch open PR metadata from GitHub via gh CLI."""
    list_cmd = [
        "gh",
        "pr",
        "list",
        "-R",
        repo,
        "--state",
        "open",
        "--limit",
        "50",
        "--json",
        "number,title,author,baseRefName,headRefName,baseRefOid,headRefOid,isCrossRepository,isDraft,state,mergeable,mergeStateStatus,body,files,comments,reviews,statusCheckRollup,url",
    ]
    proc = runner(list_cmd)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise PrAuditError(f"gh pr list failed for {repo}: {detail}")
    try:
        raw_prs = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise PrAuditError(f"invalid JSON from gh pr list: {proc.stdout!r}") from exc
    if not isinstance(raw_prs, list):
        raise PrAuditError("expected JSON list from gh pr list")

    if raw_prs:
        thread_counts = _fetch_unresolved_threads_map(repo, runner=runner)
        for item in raw_prs:
            if isinstance(item, dict) and "number" in item and "unresolved_threads" not in item:
                item["unresolved_threads"] = thread_counts.get(int(item["number"]), 0)

    return parse_pr_snapshots(raw_prs)


def _best_ack_for_pr(pr: PullRequestSnapshot) -> AgentAckReport:
    """Resolve AGENT_ACK from PR body or trusted comments (author or reviewer bots)."""
    candidates: list[str] = [pr.body]
    for comment in reversed(pr.comments):
        if comment.author is not None and comment.author != pr.author and comment.author not in _TRUSTED_BOT_ACTORS:
            continue
        candidates.append(comment.body)

    first_invalid: AgentAckReport | None = None
    for text in candidates:
        if not text:
            continue
        rep = validate_agent_ack(text)
        if rep.valid:
            return rep
        if rep.present and first_invalid is None:
            first_invalid = rep
    return first_invalid or validate_agent_ack("")


def _resolve_intra_repo_heads(prs: list[PullRequestSnapshot]) -> dict[str, PullRequestSnapshot]:
    """Map unique non-fork head branches (excluding base branches like main/master)."""
    counts: dict[str, int] = {}
    candidates: dict[str, PullRequestSnapshot] = {}
    for pr in prs:
        if pr.is_cross_repository or not pr.head_ref_name or pr.head_ref_name in ("main", "master"):
            continue
        counts[pr.head_ref_name] = counts.get(pr.head_ref_name, 0) + 1
        candidates[pr.head_ref_name] = pr
    return {name: pr for name, pr in candidates.items() if counts[name] == 1}


def _find_parent_pr(
    pr: PullRequestSnapshot,
    by_head_branch: dict[str, PullRequestSnapshot],
) -> PullRequestSnapshot | None:
    parent = by_head_branch.get(pr.base_ref_name)
    if parent is None or parent.number == pr.number:
        return None
    return parent


def _is_ancestor_in_clean_stack(
    ancestor: PullRequestSnapshot,
    descendant: PullRequestSnapshot,
    by_head_branch: dict[str, PullRequestSnapshot],
) -> bool:
    cur: PullRequestSnapshot | None = descendant
    visited: set[int] = set()
    while cur is not None and cur.number not in visited:
        visited.add(cur.number)
        parent = _find_parent_pr(cur, by_head_branch)
        if parent is None:
            return False
        if not cur.base_ref_oid or not parent.head_ref_oid or cur.base_ref_oid != parent.head_ref_oid:
            return False
        if parent.number == ancestor.number:
            return True
        cur = parent
    return False


def audit_pull_requests(
    prs: list[PullRequestSnapshot],
    *,
    require_agent_ack: bool = True,
) -> list[PullRequestAuditResult]:
    """Audit all open PRs for semantic collisions, stacked base drift, CI, and AGENT_ACK."""
    by_head_branch = _resolve_intra_repo_heads(prs)
    ack_by_num = {pr.number: _best_ack_for_pr(pr) for pr in prs}
    findings_map: dict[int, list[AuditFinding]] = {pr.number: [] for pr in prs}

    # 1. Per-PR GitHub readiness, CI, Threads, AGENT_ACK, and Stacked Base checks
    for pr in prs:
        f_list = findings_map[pr.number]
        if pr.mergeable == "CONFLICTING":
            f_list.append(
                AuditFinding(
                    "MERGEABLE_CONFLICT",
                    "critical",
                    "GitHub reports merge conflict with base branch",
                )
            )
        elif pr.mergeable == "UNKNOWN":
            f_list.append(
                AuditFinding(
                    "MERGEABLE_UNKNOWN",
                    "warning",
                    "GitHub mergeability is still computing (UNKNOWN); re-check before merge",
                )
            )
        if pr.checks_summary == "FAILURE":
            f_list.append(
                AuditFinding("CI_FAILED", "critical", "Required CI check run(s) failed")
            )
        elif pr.checks_summary in ("PENDING", "NONE"):
            f_list.append(
                AuditFinding(
                    "CI_NOT_GREEN",
                    "warning",
                    f"CI checks status is {pr.checks_summary} (not completed success)",
                )
            )
        if pr.unresolved_threads > 0:
            f_list.append(
                AuditFinding(
                    "UNRESOLVED_THREADS",
                    "critical",
                    f"{pr.unresolved_threads} unresolved review thread(s) remain",
                )
            )

        ack = ack_by_num[pr.number]
        if not ack.present or not ack.valid:
            severity = "critical" if require_agent_ack else "warning"
            detail = "; ".join(ack.errors) if ack.errors else "missing AGENT_ACK"
            f_list.append(
                AuditFinding("AGENT_ACK_INVALID", severity, f"AGENT_ACK check failed: {detail}")
            )

        parent = _find_parent_pr(pr, by_head_branch)
        if parent is not None and pr.base_ref_oid and parent.head_ref_oid:
            if pr.base_ref_oid != parent.head_ref_oid:
                f_list.append(
                    AuditFinding(
                        "STALE_STACKED_BASE",
                        "critical",
                        (
                            f"Stacked on PR #{parent.number} ({parent.head_ref_name}) at "
                            f"{pr.base_ref_oid[:7]}, which lags behind current head {parent.head_ref_oid[:7]}"
                        ),
                        related_prs=(parent.number,),
                    )
                )

    # 2. Pairwise cross-PR Semantic Conflict checks (catches MERGEABLE false confidence)
    for i in range(len(prs)):
        for j in range(i + 1, len(prs)):
            a = prs[i]
            b = prs[j]
            if _is_ancestor_in_clean_stack(a, b, by_head_branch) or _is_ancestor_in_clean_stack(
                b, a, by_head_branch
            ):
                continue

            overlap = sorted(set(a.files).intersection(b.files))
            if overlap:
                sample = ", ".join(overlap[:3])
                findings_map[a.number].append(
                    AuditFinding(
                        "DIRECT_FILE_OVERLAP",
                        "critical",
                        f"Shares {len(overlap)} modified file(s) with PR #{b.number} ({sample})",
                        related_prs=(b.number,),
                    )
                )
                findings_map[b.number].append(
                    AuditFinding(
                        "DIRECT_FILE_OVERLAP",
                        "critical",
                        f"Shares {len(overlap)} modified file(s) with PR #{a.number} ({sample})",
                        related_prs=(a.number,),
                    )
                )

            sibling_pairs = _directory_sibling_pairs(list(a.files), list(b.files))
            if sibling_pairs:
                pair_desc = ", ".join(f"{pa} <-> {pb}" for pa, pb in sibling_pairs[:2])
                findings_map[a.number].append(
                    AuditFinding(
                        "SIBLING_NAMESPACE_COLLISION",
                        "critical",
                        f"Parallel sibling naming collision with PR #{b.number}: {pair_desc}",
                        related_prs=(b.number,),
                    )
                )
                findings_map[b.number].append(
                    AuditFinding(
                        "SIBLING_NAMESPACE_COLLISION",
                        "critical",
                        f"Parallel sibling naming collision with PR #{a.number}: {pair_desc}",
                        related_prs=(a.number,),
                    )
                )

            same_base = (
                bool(a.base_ref_oid)
                and a.base_ref_oid == b.base_ref_oid
                and a.base_ref_name == b.base_ref_name
            )
            if same_base:
                a_contracts = [f for f in a.files if _is_contract_file(f)]
                b_contracts = [f for f in b.files if _is_contract_file(f)]
                if a_contracts or b_contracts:
                    findings_map[a.number].append(
                        AuditFinding(
                            "PARALLEL_SAME_BASE_CONTRACT_DIVERGENCE",
                            "critical",
                            f"Branched from same base SHA ({a.base_ref_oid[:7]}) as PR #{b.number} while mutating schema/contract files",
                            related_prs=(b.number,),
                        )
                    )
                    findings_map[b.number].append(
                        AuditFinding(
                            "PARALLEL_SAME_BASE_CONTRACT_DIVERGENCE",
                            "critical",
                            f"Branched from same base SHA ({b.base_ref_oid[:7]}) as PR #{a.number} while mutating schema/contract files",
                            related_prs=(a.number,),
                        )
                    )
                elif not overlap and not sibling_pairs:
                    domain_a = _isolated_factory_domain(a.files)
                    domain_b = _isolated_factory_domain(b.files)
                    if domain_a is not None and domain_b is not None and domain_a != domain_b:
                        findings_map[a.number].append(
                            AuditFinding(
                                "PARALLEL_DISJOINT_FACTORY_DATA",
                                "info",
                                (
                                    f"Parallel branch off same base SHA ({a.base_ref_oid[:7]}) as PR #{b.number}; "
                                    f"strictly isolated disjoint data domains ({domain_a} vs {domain_b})"
                                ),
                                related_prs=(b.number,),
                            )
                        )
                        findings_map[b.number].append(
                            AuditFinding(
                                "PARALLEL_DISJOINT_FACTORY_DATA",
                                "info",
                                (
                                    f"Parallel branch off same base SHA ({b.base_ref_oid[:7]}) as PR #{a.number}; "
                                    f"strictly isolated disjoint data domains ({domain_b} vs {domain_a})"
                                ),
                                related_prs=(a.number,),
                            )
                        )
                    else:
                        findings_map[a.number].append(
                            AuditFinding(
                                "PARALLEL_SAME_BASE",
                                "warning",
                                f"Parallel branch off same base SHA ({a.base_ref_oid[:7]}) as PR #{b.number}; reconcile order before batch-merging",
                                related_prs=(b.number,),
                            )
                        )
                        findings_map[b.number].append(
                            AuditFinding(
                                "PARALLEL_SAME_BASE",
                                "warning",
                                f"Parallel branch off same base SHA ({b.base_ref_oid[:7]}) as PR #{a.number}; reconcile order before batch-merging",
                                related_prs=(a.number,),
                            )
                        )

    # 3. Assign initial verdicts and transitively propagate blocks across multi-hop stacked PRs
    verdict_by_num: dict[int, str] = {}
    for pr in prs:
        f_list = findings_map[pr.number]
        has_semantic_critical = any(
            f.severity == "critical"
            and f.code
            in (
                "DIRECT_FILE_OVERLAP",
                "SIBLING_NAMESPACE_COLLISION",
                "PARALLEL_SAME_BASE_CONTRACT_DIVERGENCE",
                "STALE_STACKED_BASE",
            )
            for f in f_list
        )
        has_any_critical = any(f.severity == "critical" for f in f_list)
        has_warning = any(f.severity == "warning" for f in f_list)

        if has_semantic_critical:
            verdict = "RECONCILE_REQUIRED"
        elif has_any_critical:
            verdict = "BLOCKED"
        elif pr.is_draft:
            verdict = "MERGE_WITH_CAUTION" if has_warning else "READY_TO_PROMOTE_AND_MERGE"
        elif has_warning:
            verdict = "MERGE_WITH_CAUTION"
        else:
            verdict = "READY_TO_MERGE"
        verdict_by_num[pr.number] = verdict

    changed = True
    while changed:
        changed = False
        for pr in prs:
            parent = _find_parent_pr(pr, by_head_branch)
            if parent is None:
                continue
            parent_verdict = verdict_by_num.get(parent.number)
            if parent_verdict in ("RECONCILE_REQUIRED", "BLOCKED"):
                already = any(f.code == "STACKED_PARENT_NOT_READY" for f in findings_map[pr.number])
                if not already:
                    findings_map[pr.number].append(
                        AuditFinding(
                            "STACKED_PARENT_NOT_READY",
                            "critical",
                            f"Parent PR #{parent.number} has verdict {parent_verdict}",
                            related_prs=(parent.number,),
                        )
                    )
                    verdict_by_num[pr.number] = "BLOCKED"
                    changed = True

    return [
        PullRequestAuditResult(
            pr=pr,
            agent_ack=ack_by_num[pr.number],
            verdict=verdict_by_num[pr.number],
            findings=tuple(findings_map[pr.number]),
        )
        for pr in prs
    ]


def render_markdown_report(results: list[PullRequestAuditResult]) -> str:
    """Render an executive Pre-Merge Audit table + detailed findings."""
    if not results:
        return "## PR Semantic Audit\n\nNo open pull requests found.\n"

    lines = [
        "## PR Semantic Audit (Pre-Merge Verdict)",
        "",
        "| PR | Title | Author | Base -> Head SHA | GitHub / Checks | AGENT_ACK | Pre-Merge Audit Verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for res in results:
        pr = res.pr
        base_disp = _escape_md_cell(pr.base_ref_name)
        head_short = pr.head_ref_oid[:7] if pr.head_ref_oid else "-"
        draft_tag = "Draft, " if pr.is_draft else ""
        gh_status = f"{draft_tag}{pr.mergeable}, {pr.merge_state_status}, CI={pr.checks_summary}, reviews={pr.review_count}"
        ack_status = "VALID" if res.agent_ack.valid else ("INVALID" if res.agent_ack.present else "MISSING")
        lines.append(
            f"| #{pr.number} | {_escape_md_cell(pr.title)} | {_escape_md_cell(pr.author)} | `{base_disp} -> {head_short}` | `{gh_status}` | `{ack_status}` | **{res.verdict}** |"
        )

    details: list[str] = []
    for res in results:
        if not res.findings:
            continue
        details.append(f"### PR #{res.pr.number}: {res.verdict}")
        for f in res.findings:
            details.append(f"- **[{f.severity.upper()}] `{f.code}`**: {f.message}")

    if details:
        lines.extend(["", *details])
    lines.append("")
    return "\n".join(lines)
