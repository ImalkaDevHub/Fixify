import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.repositories import scan as scan_repository
from app.scanner.classify import fingerprint
from app.scanner.contract import ArtifactResult, CheckResult, FindingResult, ScanResult
from app.worker.persistence import persist_result

NOW = datetime(2026, 5, 1, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def finding(name: str, severity: str = "medium", artifact_key: str | None = None):
    return FindingResult(
        check_type="console_errors",
        finding_type="console_error",
        title=f"Finding {name}",
        description=f"Observed {name}",
        severity=severity,  # type: ignore[arg-type]
        confidence="confirmed",
        affected_url="https://example.com/",
        evidence={"message": name},
        fingerprint=fingerprint("console_error", name),
        artifact_key=artifact_key,
    )


def scan_result(
    findings: list[FindingResult], *, with_screenshot: bool = True, outcome: str = "completed"
) -> ScanResult:
    checks = [
        CheckResult(
            name="Page navigation",
            check_type="page_navigation",
            status="passed",
            target_url="https://example.com/",
            summary="ok",
            started_at=NOW,
            finished_at=NOW,
            duration_ms=10,
        ),
        CheckResult(
            name="JavaScript console errors",
            check_type="console_errors",
            status="failed" if findings else "passed",
            target_url="https://example.com/",
            summary="x",
            started_at=NOW,
            finished_at=NOW,
            duration_ms=1,
        ),
    ]
    artifacts = []
    if with_screenshot:
        artifacts.append(
            ArtifactResult(
                key="screenshot",
                kind="screenshot",
                file_name="screenshot.png",
                content_type="image/png",
                size_bytes=len(PNG),
                width=1280,
                height=800,
                sha256="0" * 64,
            )
        )
    return ScanResult(
        requested_url="https://example.com/",
        final_url="https://example.com/",
        started_at=NOW,
        finished_at=NOW,
        outcome=outcome,  # type: ignore[arg-type]
        checks=checks,
        findings=findings,
        artifacts=artifacts,
    )


async def complete_run(
    session_factory,
    run_id: uuid.UUID,
    result: ScanResult,
    work_dir: Path,
    artifact_root: Path,
) -> int:
    """Claim a queued run and store a result for it, as the worker would."""
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "screenshot.png").write_bytes(PNG)
    async with session_factory() as session:
        attempt = await scan_repository.claim_run(session, run_id, NOW)
    assert attempt is not None
    async with session_factory() as session:
        stored = await persist_result(
            session,
            run_id=run_id,
            attempt=attempt,
            result=result,
            work_dir=work_dir,
            artifact_root=artifact_root,
            max_artifact_bytes=1_000_000,
        )
    assert stored
    return attempt
