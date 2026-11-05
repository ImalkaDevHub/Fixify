"""Artifact storage on the local filesystem.

Names are generated server-side from UUIDs; callers never supply paths. Every resolved path is
checked to stay inside the artifact directory before it is read, written, or deleted.
"""

import logging
import shutil
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


class ArtifactPathError(ValueError):
    pass


def storage_key(run_id: uuid.UUID, artifact_id: uuid.UUID, suffix: str = ".png") -> str:
    return f"{run_id}/{artifact_id}{suffix}"


def resolve_artifact_path(root: Path, key: str) -> Path:
    """Map a stored key to a path, refusing anything that is not "<uuid>/<uuid>.<ext>"."""
    parts = key.split("/")
    if len(parts) != 2:
        raise ArtifactPathError("Invalid artifact key.")
    run_part, file_part = parts
    stem, dot, suffix = file_part.partition(".")
    try:
        uuid.UUID(run_part)
        uuid.UUID(stem)
    except ValueError as error:
        raise ArtifactPathError("Invalid artifact key.") from error
    if not dot or suffix not in ("png",):
        raise ArtifactPathError("Invalid artifact key.")
    base = root.resolve()
    path = (base / run_part / file_part).resolve()
    if not path.is_relative_to(base):
        raise ArtifactPathError("Artifact path escapes the artifact directory.")
    return path


def store_file(root: Path, source: Path, key: str, max_bytes: int) -> int:
    """Copy a scanner output file into the store. Returns the stored size in bytes."""
    size = source.stat().st_size
    if size > max_bytes:
        raise ArtifactPathError("Artifact exceeds the size limit.")
    destination = resolve_artifact_path(root, key)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    shutil.copyfile(source, temporary)
    temporary.replace(destination)
    return size


def delete_run_artifacts(root: Path, run_id: uuid.UUID) -> None:
    base = root.resolve()
    directory = (base / str(run_id)).resolve()
    if directory.is_relative_to(base) and directory != base and directory.is_dir():
        shutil.rmtree(directory, ignore_errors=True)


def cleanup_expired(root: Path, retention_days: int, known_run_ids: set[str] | None = None) -> int:
    """Delete run directories older than the retention period, or not belonging to a run.

    Returns the number of directories removed. Only "<uuid>" directories are considered, so
    unrelated files placed in the directory are left alone.
    """
    base = root.resolve()
    if not base.is_dir():
        return 0
    cutoff = time.time() - retention_days * 86_400
    removed = 0
    for entry in base.iterdir():
        try:
            uuid.UUID(entry.name)
        except ValueError:
            continue
        if not entry.is_dir():
            continue
        orphaned = known_run_ids is not None and entry.name not in known_run_ids
        if orphaned or entry.stat().st_mtime < cutoff:
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
    if removed:
        logger.info("Removed %d expired artifact directories", removed)
    return removed


MARKER_FILE = ".fixify-database"


def database_identity(database_url: str) -> str:
    """Stable, credential-free identity of a database (backend, host, port, name)."""
    import hashlib

    from sqlalchemy.engine import make_url

    url = make_url(database_url)
    raw = f"{url.get_backend_name()}://{url.host or ''}:{url.port or ''}/{url.database or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def artifact_root_state(root: Path, identity: str) -> str:
    """Whether this artifact directory belongs to the worker's database.

    Returns "owned" (marker matches), "claimed" (no marker yet: it is written now) or "foreign"
    (marker names another database). Orphan cleanup must only run for "owned", otherwise a worker
    pointed at a different database would delete another environment's screenshots.
    """
    base = root.resolve()
    marker = base / MARKER_FILE
    if not marker.is_file():
        base.mkdir(parents=True, exist_ok=True)
        marker.write_text(identity + "\n", encoding="utf-8")
        return "claimed"
    if marker.read_text(encoding="utf-8").strip() == identity:
        return "owned"
    return "foreign"
