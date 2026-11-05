"""AI analysis of scanner findings. The model sees only Fixify's recorded (and already redacted)
evidence; nothing is invented when evidence or AI is unavailable."""

import json
import logging
import uuid

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import (
    ANALYSIS_SCHEMA,
    ANALYSIS_SYSTEM,
    AnalysisOutput,
    redact_secrets,
    untrusted,
)
from app.ai.provider import AIError, AIProvider
from app.core.config import Settings
from app.db.models.platform import AIAnalysis, BackgroundJob
from app.db.models.project import Project
from app.db.models.scan import Finding, TestRun
from app.integrations.github import GitHubError
from app.repositories import scan as scan_repository
from app.services import github as github_service
from app.services import jobs as job_service
from app.services import notifications
from app.services.jobs import JobError
from app.services.repository_files import path_overview

logger = logging.getLogger(__name__)
_MAX_EVIDENCE_CHARS = 12_000
_MAX_OTHER_FINDINGS = 40


class AnalysisError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def request_analysis(
    session: AsyncSession, owner_id: uuid.UUID, finding_id: uuid.UUID, config: Settings
) -> BackgroundJob:
    finding = await scan_repository.get_owned_finding(session, finding_id, owner_id)
    if finding is None:
        raise AnalysisError("Finding not found.", 404)
    if not config.ai_configured:
        raise AnalysisError("AI analysis is not configured on this server.", 503)
    try:
        job, _ = await job_service.enqueue(
            session,
            kind="analyze_finding",
            owner_id=owner_id,
            project_id=finding.project_id,
            subject_id=finding.id,
            config=config,
        )
    except job_service.JobLimitError as error:
        raise AnalysisError(error.message, 429) from error
    return job


async def latest_analysis(
    session: AsyncSession, owner_id: uuid.UUID, finding_id: uuid.UUID
) -> AIAnalysis | None:
    return await session.scalar(
        select(AIAnalysis)
        .join(Project, Project.id == AIAnalysis.project_id)
        .where(AIAnalysis.finding_id == finding_id, Project.owner_id == owner_id)
        .order_by(AIAnalysis.created_at.desc())
        .limit(1)
    )


def _evidence_block(finding: Finding) -> str:
    raw = json.dumps(finding.evidence or {}, ensure_ascii=False, sort_keys=True)[
        :_MAX_EVIDENCE_CHARS
    ]
    text, _ = redact_secrets(raw)
    return text


def _finding_text(finding: Finding, run: TestRun | None) -> str:
    lines = [
        f"finding_id: {finding.id}",
        f"check: {finding.check_type}",
        f"type: {finding.finding_type}",
        f"severity: {finding.severity}",
        f"confidence: {finding.confidence}",
        f"title: {finding.title}",
        f"description: {finding.description}",
        f"affected_url: {finding.affected_url or '-'}",
        f"http_status: {finding.http_status if finding.http_status is not None else '-'}",
    ]
    if run is not None:
        lines += [f"scanned_url: {run.target_url}", f"final_url: {run.final_url or '-'}"]
    lines.append(f"evidence_json: {_evidence_block(finding)}")
    text, _ = redact_secrets("\n".join(lines))
    return text


async def _repository_paths(
    session: AsyncSession, owner_id: uuid.UUID, project: Project, finding: Finding, config: Settings
) -> list[str]:
    """Readable repository paths, or [] when no repository is connected or GitHub fails."""
    if not project.repo_full_name or not config.github_configured:
        return []
    try:
        connected = await github_service.open_client(session, owner_id, config)
        async with connected.client as client:
            snap = await github_service.snapshot(client, project, config)
    except github_service.GitHubServiceError as error:
        logger.info("Analysis without repository context: %s", error.message)
        return []
    except GitHubError as error:
        await github_service.handle_auth_failure(session, owner_id, error)
        logger.info("Analysis without repository context: %s", error.public_message)
        return []
    return path_overview(snap.entries, finding)


async def run_analysis(
    session: AsyncSession, job: BackgroundJob, provider: AIProvider | None, config: Settings
) -> uuid.UUID:
    """Worker handler for 'analyze_finding'. Returns the new analysis ID."""
    if provider is None:
        raise JobError("AI analysis is not configured on this server.")
    finding = await session.get(Finding, job.subject_id)
    project = await session.get(Project, job.project_id)
    if finding is None or project is None or project.owner_id != job.owner_id:
        raise JobError("The finding no longer exists.")
    run = await session.get(TestRun, finding.test_run_id)
    others = [
        f
        for f in await scan_repository.list_run_findings(
            session, finding.test_run_id, severity=None, limit=_MAX_OTHER_FINDINGS + 1, offset=0
        )
        if f.id != finding.id
    ][:_MAX_OTHER_FINDINGS]
    paths = await _repository_paths(session, job.owner_id, project, finding, config)

    parts = [
        "Analyze this finding from Fixify's browser scan.",
        untrusted("finding", _finding_text(finding, run)),
        untrusted(
            "other_findings",
            "\n".join(
                redact_secrets(
                    f"{f.id} | {f.finding_type} | {f.severity} | {f.title} | "
                    f"{f.affected_url or '-'}"
                )[0]
                for f in others
            )
            or "(none)",
        ),
    ]
    if paths:
        parts.append(
            untrusted("repository_paths", "\n".join(paths), repository=project.repo_full_name or "")
        )
    else:
        parts.append("No repository is connected: return an empty suggested_locations list.")

    try:
        result = await provider.generate_json(
            system=ANALYSIS_SYSTEM,
            user_content="\n\n".join(parts),
            schema=ANALYSIS_SCHEMA,
            max_tokens=config.ai_max_output_tokens,
        )
        output = AnalysisOutput.model_validate(result.data)
    except AIError as error:
        raise JobError(error.public_message, retryable=error.retryable) from error
    except ValidationError as error:
        raise JobError(
            "The AI response did not match the expected format.", retryable=True
        ) from error

    allowed_paths = set(paths)
    other_ids = {str(f.id) for f in others}
    analysis = AIAnalysis(
        project_id=project.id,
        finding_id=finding.id,
        summary=output.summary,
        technical_explanation=output.technical_explanation,
        root_cause=output.root_cause,
        user_impact=output.user_impact,
        why_it_matters=output.why_it_matters,
        recommended_solution=output.recommended_solution,
        fix_complexity=output.fix_complexity,
        confidence=output.confidence,
        # Never trust model-supplied paths or IDs: keep only those Fixify provided.
        suggested_locations=[
            location.model_dump()
            for location in output.suggested_locations
            if location.path in allowed_paths
        ],
        evidence_refs=[ref[:300] for ref in output.evidence_refs][:20],
        related_finding_ids=[fid for fid in output.related_finding_ids if fid in other_ids],
        provider=result.provider,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
    session.add(analysis)
    await session.flush()
    await notifications.notify(
        session,
        user_id=job.owner_id,
        kind="analysis_completed",
        title=f"AI analysis ready: {finding.title}",
        body=output.summary,
        link=f"/findings/{finding.id}",
        project_id=project.id,
        dedupe_key=f"analysis:{job.id}",
    )
    return analysis.id
