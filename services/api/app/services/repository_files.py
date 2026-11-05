"""Which repository files Fixify may read, and which ones are likely relevant to a finding."""

import posixpath
import re
from collections.abc import Iterable
from urllib.parse import urlsplit

from app.db.models.scan import Finding
from app.integrations.github import TreeEntry

SOURCE_EXTENSIONS = frozenset(
    {
        ".html",
        ".htm",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".vue",
        ".svelte",
        ".astro",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".json",
        ".py",
        ".rb",
        ".php",
        ".go",
        ".java",
        ".cs",
        ".erb",
        ".ejs",
        ".hbs",
        ".njk",
        ".liquid",
        ".twig",
        ".jinja",
        ".jinja2",
        ".j2",
        ".md",
        ".mdx",
        ".xml",
        ".txt",
        ".toml",
        ".yml",
        ".yaml",
        ".svg",
    }
)
# Never read, even if the user asks: secrets, dependencies, build output, VCS internals.
_DENIED_SEGMENTS = frozenset(
    {
        ".git",
        "node_modules",
        "vendor",
        "dist",
        "build",
        ".next",
        "out",
        "coverage",
        "__pycache__",
        ".venv",
        "venv",
        "bower_components",
        ".terraform",
        "secrets",
    }
)
_DENIED_NAMES = re.compile(
    r"(?i)^(\.env(\..*)?|.*\.(pem|key|p12|pfx|crt|cer|jks|keystore)|id_rsa.*|id_ed25519.*|"
    r".*secrets?\.(json|ya?ml|toml)|credentials.*|\.npmrc|\.pypirc|\.netrc|"
    r"package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|composer\.lock|.*\.min\.(js|css))$"
)
_HEAD_FINDINGS = frozenset(
    {
        "missing_title",
        "missing_viewport_meta",
        "missing_favicon",
        "missing_meta_description",
        "missing_h1",
        "multiple_h1",
    }
)
_HEAD_FILES = re.compile(
    r"(?i)(^|/)(index\.html?|layout\.(tsx|jsx|js|ts|vue|svelte|astro)|_document\.(tsx|jsx|js)|"
    r"_app\.(tsx|jsx|js)|app\.html|base\.html|head\.(tsx|jsx|html|vue)|header\.|"
    r"default\.(vue|html|hbs|njk)|main\.(html|tsx|jsx))"
)


def is_readable_path(path: str) -> bool:
    parts = path.split("/")
    if any(part in _DENIED_SEGMENTS for part in parts[:-1]):
        return False
    name = parts[-1]
    if _DENIED_NAMES.match(name):
        return False
    return posixpath.splitext(name)[1].lower() in SOURCE_EXTENSIONS


def readable_entries(entries: Iterable[TreeEntry], max_bytes: int) -> list[TreeEntry]:
    return [entry for entry in entries if is_readable_path(entry.path) and entry.size <= max_bytes]


def _url_terms(url: str | None) -> set[str]:
    if not url:
        return set()
    path = urlsplit(url).path
    terms = set()
    for segment in path.split("/"):
        if not segment:
            continue
        stem = posixpath.splitext(segment)[0].lower()
        terms.add(segment.lower())
        if len(stem) >= 3:
            terms.add(stem)
    return terms


def finding_terms(finding: Finding) -> set[str]:
    evidence = finding.evidence or {}
    terms = _url_terms(finding.affected_url)
    for key in ("url", "source_url", "resource_url", "page_url"):
        value = evidence.get(key)
        if isinstance(value, str):
            terms |= _url_terms(value)
    stack = evidence.get("stack") or evidence.get("location") or ""
    if isinstance(stack, str):
        for match in re.findall(r"([A-Za-z0-9_.-]+\.(?:js|jsx|ts|tsx|mjs|vue|svelte))", stack):
            terms.add(match.lower())
            terms.add(posixpath.splitext(match)[0].lower())
    return {term for term in terms if term not in {"index", "www", "http", "https"}}


def rank_paths(
    entries: list[TreeEntry], finding: Finding, preferred: Iterable[str] = ()
) -> list[TreeEntry]:
    """Most plausible files first. Paths the analysis suggested win; then name matches."""
    preferred_set = set(preferred)
    terms = finding_terms(finding)
    scored: list[tuple[int, TreeEntry]] = []
    for entry in entries:
        lower = entry.path.lower()
        name = lower.rsplit("/", 1)[-1]
        stem = posixpath.splitext(name)[0]
        score = 0
        if entry.path in preferred_set:
            score += 100
        if name in terms:
            score += 40
        elif stem in terms:
            score += 20
        score += 5 * sum(1 for term in terms if len(term) >= 4 and term in lower)
        if finding.finding_type in _HEAD_FINDINGS and _HEAD_FILES.search(lower):
            score += 30
        if finding.finding_type in ("broken_link", "possibly_broken_link", "broken_image") and (
            name.endswith((".html", ".htm", ".tsx", ".jsx", ".vue", ".svelte", ".md", ".mdx"))
        ):
            score += 2
        if score:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], len(item[1].path), item[1].path))
    return [entry for _, entry in scored]


def path_overview(entries: list[TreeEntry], finding: Finding, limit: int = 300) -> list[str]:
    """A bounded list of readable paths for the model, relevant ones first."""
    ranked = rank_paths(entries, finding)
    seen = {entry.path for entry in ranked}
    rest = sorted((entry.path for entry in entries if entry.path not in seen), key=len)
    return ([entry.path for entry in ranked] + rest)[:limit]
