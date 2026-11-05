"""AI fix proposals, human review, and pull requests.

Workflow: finding -> (analysis) -> proposed fix -> human review -> approval -> new branch ->
commit -> pull request. Nothing is pushed before a person approves it, nothing is merged, and
every edit is re-applied against the current file contents when the branch is created.
"""

import logging
import uuid
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import FIX_SCHEMA, FIX_SYSTEM, FixEdit, FixOutput, redact_secrets, untrusted
from app.ai.provider import AIError, AIProvider
from app.core.config import Settings
from app.db.models.platform import (
    AIAnalysis,
    BackgroundJob,
    FixProposal,
    FixReview,
    PullRequest,
)
from app.db.models.project import Project
from app.db.models.scan import Finding
from app.db.models.user import User
from app.integrations.github import GitHubError, safe_repo_path
from app.repositories import scan as scan_repository
from app.services import github as github_service
from app.services import jobs as job_service
from app.services import notifications
from app.services.fix_validation import (
    EditError,
    apply_edit,
    apply_edits,
    excerpt,
    language_for,
    validate,
)
from app.services.jobs import JobError
from app.services.repository_files import is_readable_path, rank_paths

logger = logging.getLogger(__name__)

REVIEWABLE = ("pending_review",)
TRANSITIONS = {
    "approve": ({"pending_review"}, "approved"),
    "reject": ({"pending_review", "approved", "failed_validation"}, "rejected"),
    "reopen": ({"rejected", "superseded"}, "pending_review"),
}


class FixError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def utcnow() -> datetime:
    return datetime.now(UTC)


# --- Queries --------------------------------------------------------------------------------


async def get_owned_fix(
    session: AsyncSession, owner_id: uuid.UUID, fix_id: uuid.UUID
) -> FixProposal | None:
    return await session.scalar(
        select(FixProposal)
        .join(Project, Project.id == FixProposal.project_id)
        .where(FixProposal.id == fix_id, Project.owner_id == owner_id)
        .execution_options(populate_existing=True)
    )


async def list_fixes(
    session: AsyncSession,
    owner_id: uuid.UUID,
    *,
    finding_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[FixProposal]:
    query = (
        select(FixProposal)
        .join(Project, Project.id == FixProposal.project_id)
        .where(Project.owner_id == owner_id)
    )
    if finding_id is not None:
        query = query.where(FixProposal.finding_id == finding_id)
    if project_id is not None:
        query = query.where(FixProposal.project_id == project_id)
    if status is not None:
        query = query.where(FixProposal.status == status)
    result = await session.scalars(
        query.order_by(
            FixProposal.created_at.desc(), FixProposal.version.desc(), FixProposal.id.desc()
        )
        .limit(limit)
        .offset(offset)
    )
    return list(result)


async def reviews_for(session: AsyncSession, fix_id: uuid.UUID) -> list[FixReview]:
    result = await session.scalars(
        select(FixReview).where(FixReview.fix_id == fix_id).order_by(FixReview.created_at)
    )
    return list(result)


async def pull_request_for(session: AsyncSession, fix_id: uuid.UUID) -> PullRequest | None:
    return await session.scalar(select(PullRequest).where(PullRequest.fix_id == fix_id))


# --- Requesting a fix -----------------------------------------------------------------------


async def request_fix(
    session: AsyncSession,
    owner_id: uuid.UUID,
    finding_id: uuid.UUID,
    *,
    file_paths: list[str] | None,
    instructions: str | None,
    parent_fix_id: uuid.UUID | None,
    config: Settings,
) -> BackgroundJob:
    finding = await scan_repository.get_owned_finding(session, finding_id, owner_id)
    if finding is None:
        raise FixError("Finding not found.", 404)
    project = await session.get(Project, finding.project_id)
    assert project is not None
    if not config.ai_configured:
        raise FixError("AI fix generation is not configured on this server.", 503)
    if not config.github_configured:
        raise FixError("GitHub integration is not configured on this server.", 503)
    if not project.repo_full_name:
        raise FixError("Connect a GitHub repository to this project first.", 409)
    if await github_service.get_connection(session, owner_id) is None:
        raise FixError("Connect your GitHub account first.", 409)
    if parent_fix_id is not None:
        parent = await get_owned_fix(session, owner_id, parent_fix_id)
        if parent is None or parent.finding_id != finding.id:
            raise FixError("The fix to regenerate was not found for this finding.", 404)
    paths: list[str] = []
    for raw in file_paths or []:
        path = safe_repo_path(raw)
        if path is None or not is_readable_path(path):
            raise FixError(f"Fixify does not read the file {raw!r}.", 422)
        paths.append(path)
    try:
        job, _ = await job_service.enqueue(
            session,
            kind="generate_fix",
            owner_id=owner_id,
            project_id=project.id,
            subject_id=finding.id,
            payload={
                "file_paths": paths,
                "instructions": (instructions or "")[:2_000],
                "parent_fix_id": str(parent_fix_id) if parent_fix_id else None,
            },
            config=config,
        )
    except job_service.JobLimitError as error:
        raise FixError(error.message, 429) from error
    return job


def _analysis_text(analysis: AIAnalysis | None) -> str:
    if analysis is None:
        return "(no AI analysis yet)"
    return (
        f"summary: {analysis.summary}\nroot_cause: {analysis.root_cause}\n"
        f"recommended_solution: {analysis.recommended_solution}"
    )


async def run_fix_generation(
    session: AsyncSession, job: BackgroundJob, provider: AIProvider | None, config: Settings
) -> uuid.UUID:
    """Worker handler for 'generate_fix'. Returns the new fix proposal ID."""
    if provider is None:
        raise JobError("AI fix generation is not configured on this server.")
    finding = await session.get(Finding, job.subject_id)
    project = await session.get(Project, job.project_id)
    if finding is None or project is None or project.owner_id != job.owner_id:
        raise JobError("The finding no longer exists.")
    if not project.repo_full_name:
        raise JobError("The project has no connected repository.")
    analysis = await session.scalar(
        select(AIAnalysis)
        .where(AIAnalysis.finding_id == finding.id)
        .order_by(AIAnalysis.created_at.desc())
        .limit(1)
    )
    payload = job.payload or {}
    parent = None
    if payload.get("parent_fix_id"):
        parent = await session.get(FixProposal, uuid.UUID(payload["parent_fix_id"]))

    try:
        connected = await github_service.open_client(session, job.owner_id, config)
    except github_service.GitHubServiceError as error:
        raise JobError(error.message) from error
    try:
        async with connected.client as client:
            snap = await github_service.snapshot(client, project, config)
            requested = [path for path in payload.get("file_paths") or []]
            if requested:
                candidates = requested
            else:
                preferred = [
                    loc.get("path", "")
                    for loc in (analysis.suggested_locations if analysis else [])
                ]
                candidates = [entry.path for entry in rank_paths(snap.entries, finding, preferred)]
            files = await github_service.read_files(client, snap, candidates, config)
    except GitHubError as error:
        await github_service.handle_auth_failure(session, job.owner_id, error)
        raise JobError(error.public_message, retryable=error.retryable) from error
    if not files:
        raise JobError(
            "Fixify could not find readable source files related to this finding. "
            "Choose the files to change and try again."
        )

    file_blocks = []
    for content in files:
        redacted, _ = redact_secrets(content.text)
        file_blocks.append(untrusted("file", redacted, path=content.path))
    parts = [
        f"Repository: {snap.full_name} (branch {snap.branch}).",
        untrusted(
            "finding",
            redact_secrets(
                f"type: {finding.finding_type}\nseverity: {finding.severity}\n"
                f"title: {finding.title}\n"
                f"description: {finding.description}\naffected_url: {finding.affected_url or '-'}\n"
                f"evidence: {finding.evidence}"
            )[0],
        ),
        untrusted("analysis", _analysis_text(analysis)),
        *file_blocks,
    ]
    if parent is not None:
        comments = [
            review.comment for review in await reviews_for(session, parent.id) if review.comment
        ]
        parts.append(
            "A previous proposal was not accepted. Reviewer feedback (from the project owner):\n"
            + ("\n".join(f"- {comment[:1000]}" for comment in comments) or "- (none)")
            + f"\nPrevious proposal title: {parent.title}"
        )
    if payload.get("instructions"):
        parts.append(f"Additional instructions from the project owner: {payload['instructions']}")

    try:
        result = await provider.generate_json(
            system=FIX_SYSTEM,
            user_content="\n\n".join(parts),
            schema=FIX_SCHEMA,
            max_tokens=config.ai_max_output_tokens,
        )
        output = FixOutput.model_validate(result.data)
    except AIError as error:
        raise JobError(error.public_message, retryable=error.retryable) from error
    except ValidationError as error:
        raise JobError(
            "The AI response did not match the expected format.", retryable=True
        ) from error
    if not output.edits:
        reason = output.cannot_fix_reason.strip() or "no reason given"
        raise JobError(f"The AI could not propose a safe fix: {reason}"[:500])

    sources = {content.path: (content.sha, content.text) for content in files}
    changes, edit_errors = apply_edits(sources, output.edits, config.github_max_files_per_fix)
    report = validate(changes, edit_errors)
    stored_changes = []
    for change in changes:
        before, after, start_line = excerpt(change.original_text, change.new_text, change.edits)
        stored_changes.append(
            {
                "path": change.path,
                "blob_sha": change.blob_sha,
                "language": language_for(change.path),
                "start_line": start_line,
                "original": before,
                "proposed": after,
                "edits": [edit.model_dump() for edit in change.edits],
            }
        )
    fix = FixProposal(
        project_id=project.id,
        finding_id=finding.id,
        analysis_id=analysis.id if analysis else None,
        parent_id=parent.id if parent else None,
        version=(parent.version + 1) if parent else 1,
        status="pending_review" if report.status != "failed" else "failed_validation",
        repo_full_name=snap.full_name,
        base_branch=snap.branch,
        base_commit_sha=snap.commit_sha,
        title=output.title[:200],
        explanation=output.explanation,
        impact=output.impact,
        confidence=output.confidence,
        validation_status=report.status,
        validation_messages=report.messages[:30],
        changes=stored_changes,
        provider=result.provider,
        model=result.model,
        created_by_id=job.owner_id,
    )
    session.add(fix)
    if parent is not None and parent.status in ("pending_review", "approved", "failed_validation"):
        parent.status = "superseded"
    await session.flush()
    failed = report.status == "failed"
    await notifications.notify(
        session,
        user_id=job.owner_id,
        kind="fix_validation_failed" if failed else "fix_ready",
        title=("Proposed fix failed validation: " if failed else "Fix ready for review: ")
        + fix.title,
        body="; ".join(report.messages[:3]) if failed else output.explanation[:300],
        link=f"/fixes/{fix.id}",
        project_id=project.id,
        dedupe_key=f"fix:{job.id}",
    )
    return fix.id


# --- Human review ---------------------------------------------------------------------------


async def review(
    session: AsyncSession,
    owner_id: uuid.UUID,
    fix_id: uuid.UUID,
    action: str,
    comment: str | None,
) -> FixProposal:
    fix = await get_owned_fix(session, owner_id, fix_id)
    if fix is None:
        raise FixError("Fix proposal not found.", 404)
    if action == "comment":
        if not (comment or "").strip():
            raise FixError("Write a comment first.", 422)
    else:
        allowed, target = TRANSITIONS[action]
        if fix.status not in allowed:
            raise FixError(
                f"A fix that is {fix.status.replace('_', ' ')} cannot be {action}d.", 409
            )
        if action == "approve" and fix.validation_status == "failed":
            raise FixError("A fix that failed validation cannot be approved. Regenerate it.", 409)
        if action == "reopen" and fix.validation_status == "failed":
            target = "failed_validation"
        fix.status = target
        fix.reviewed_by_id = owner_id
        fix.reviewed_at = utcnow()
    session.add(
        FixReview(
            fix_id=fix.id,
            user_id=owner_id,
            action=action,
            comment=(comment or "").strip()[:5_000] or None,
        )
    )
    await session.commit()
    await session.refresh(fix)
    return fix


# --- Pull requests --------------------------------------------------------------------------


def branch_name(fix: FixProposal) -> str:
    return f"fixify/fix-{str(fix.finding_id)[:8]}-{str(fix.id)[:8]}"


async def request_pull_request(
    session: AsyncSession, owner_id: uuid.UUID, fix_id: uuid.UUID, config: Settings
) -> BackgroundJob:
    fix = await get_owned_fix(session, owner_id, fix_id)
    if fix is None:
        raise FixError("Fix proposal not found.", 404)
    if fix.status != "approved":
        raise FixError("Only approved fixes can be turned into a pull request.", 409)
    if fix.validation_status == "failed":
        raise FixError("A fix that failed validation cannot be committed.", 409)
    if not config.github_configured:
        raise FixError("GitHub integration is not configured on this server.", 503)
    pr = await pull_request_for(session, fix.id)
    if pr is not None and pr.status in ("open", "merged", "closed"):
        raise FixError("A pull request already exists for this fix.", 409)
    if pr is None:
        session.add(
            PullRequest(
                fix_id=fix.id,
                project_id=fix.project_id,
                repo_full_name=fix.repo_full_name,
                branch_name=branch_name(fix),
                base_branch=fix.base_branch,
                status="creating",
            )
        )
    else:
        pr.status, pr.error = "creating", None
    await session.commit()
    job, _ = await job_service.enqueue(
        session,
        kind="create_pull_request",
        owner_id=owner_id,
        project_id=fix.project_id,
        subject_id=fix.id,
        config=config,
    )
    return job


def _no_mentions(text: str) -> str:
    # Website-derived text must not ping GitHub users or teams.
    return text.replace("@", "@​")


def pull_request_body(fix: FixProposal, finding: Finding | None, reviewer: User | None) -> str:
    lines = [
        "## Fixify proposed fix",
        "",
        f"**Finding:** {_no_mentions(finding.title) if finding else 'n/a'}"
        + (f" ({finding.severity})" if finding else ""),
        "",
        _no_mentions(fix.explanation),
        "",
        "### Impact",
        _no_mentions(fix.impact),
        "",
        f"**Validation:** {fix.validation_status}",
    ]
    lines += [f"- {_no_mentions(message)}" for message in fix.validation_messages[:10]]
    lines += [
        "",
        f"AI confidence: {fix.confidence}. Generated by {fix.model} and approved in Fixify"
        + (f" by {_no_mentions(reviewer.display_name)}" if reviewer else "")
        + ". Please review the diff and run your tests before merging.",
    ]
    return "\n".join(lines)


async def run_pull_request(
    session: AsyncSession, job: BackgroundJob, _provider: AIProvider | None, config: Settings
) -> uuid.UUID:
    """Worker handler for 'create_pull_request'. Idempotent: a retry reuses the branch and PR."""
    fix = await session.get(FixProposal, job.subject_id)
    pr = await pull_request_for(session, job.subject_id)
    if fix is None or pr is None:
        raise JobError("The fix proposal no longer exists.")
    if fix.status not in ("approved", "applied"):
        raise JobError("The fix is no longer approved; nothing was pushed.")
    try:
        connected = await github_service.open_client(session, job.owner_id, config)
    except github_service.GitHubServiceError as error:
        raise JobError(error.message) from error
    repo = fix.repo_full_name
    try:
        async with connected.client as client:
            existing_head = await client.branch_exists(repo, pr.branch_name)
            if existing_head is None:
                base_sha = await client.branch_head(repo, fix.base_branch)
                entries, _ = await client.tree(repo, base_sha)
                by_path = {entry.path: entry for entry in entries}
                new_files: list[tuple[str, str, str]] = []
                for change in fix.changes:
                    path = safe_repo_path(change["path"])
                    entry = by_path.get(path or "")
                    if entry is None:
                        raise JobError(f"{change['path']} no longer exists on {fix.base_branch}.")
                    content = await client.blob_text(repo, entry)
                    if content is None:
                        raise JobError(f"{entry.path} can no longer be read as text.")
                    text = content.text
                    try:
                        for raw_edit in change["edits"]:
                            text = apply_edit(text, FixEdit.model_validate(raw_edit))
                    except EditError as error:
                        raise JobError(
                            f"{entry.path} changed on {fix.base_branch} since the fix was "
                            "generated, so it no longer applies cleanly. Regenerate the fix."
                        ) from error
                    blob = await client.create_blob(repo, text)
                    new_files.append((entry.path, entry.mode, blob))
                tree = await client.create_tree(
                    repo, await client.commit_tree_sha(repo, base_sha), new_files
                )
                commit = await client.create_commit(
                    repo,
                    f"{fix.title}\n\nProposed by Fixify and approved by a reviewer.",
                    tree,
                    base_sha,
                )
                await client.create_branch(repo, pr.branch_name, commit)
                pr.commit_sha = commit
            else:
                pr.commit_sha = existing_head
            data = await client.find_pull_request(repo, pr.branch_name)
            if data is None:
                finding = await session.get(Finding, fix.finding_id)
                reviewer = (
                    await session.get(User, fix.reviewed_by_id) if fix.reviewed_by_id else None
                )
                data = await client.create_pull_request(
                    repo,
                    title=f"Fixify: {fix.title}"[:250],
                    body=pull_request_body(fix, finding, reviewer),
                    head=pr.branch_name,
                    base=fix.base_branch,
                )
    except GitHubError as error:
        await github_service.handle_auth_failure(session, job.owner_id, error)
        if not error.retryable:
            pr.status, pr.error = "failed", error.public_message[:500]
            await session.commit()
        raise JobError(error.public_message, retryable=error.retryable) from error
    except JobError as error:
        pr.status, pr.error = "failed", error.public_message[:500]
        await session.commit()
        raise

    _apply_pull_request_state(pr, data)
    fix.status = "applied"
    await notifications.notify(
        session,
        user_id=job.owner_id,
        kind="pull_request_created",
        title=f"Pull request #{pr.number} opened: {fix.title}",
        body=f"{repo} · {pr.branch_name} → {fix.base_branch}",
        link=f"/fixes/{fix.id}",
        project_id=fix.project_id,
        dedupe_key=f"pr:{pr.id}",
    )
    return pr.id


def _apply_pull_request_state(pr: PullRequest, data: dict) -> None:
    pr.number = int(data.get("number") or 0) or None
    pr.url = str(data.get("html_url") or "")[:500] or None
    if data.get("merged_at") or data.get("merged"):
        pr.status = "merged"
    elif data.get("state") == "closed":
        pr.status = "closed"
    else:
        pr.status = "open"
    pr.error = None
    pr.last_synced_at = utcnow()


async def refresh_pull_request(
    session: AsyncSession, owner_id: uuid.UUID, fix_id: uuid.UUID, config: Settings
) -> PullRequest:
    fix = await get_owned_fix(session, owner_id, fix_id)
    pr = await pull_request_for(session, fix_id) if fix else None
    if fix is None or pr is None or pr.number is None:
        raise FixError("No pull request exists for this fix yet.", 404)
    try:
        connected = await github_service.open_client(session, owner_id, config)
        async with connected.client as client:
            data = await client.pull_request(fix.repo_full_name, pr.number)
    except github_service.GitHubServiceError as error:
        raise FixError(error.message, error.status_code) from error
    except GitHubError as error:
        await github_service.handle_auth_failure(session, owner_id, error)
        raise FixError(
            error.public_message, 502 if error.status >= 500 else error.status
        ) from error
    _apply_pull_request_state(pr, data)
    await session.commit()
    await session.refresh(pr)
    return pr
