"""Applying AI-proposed edits safely and checking the result.

Edits are search-and-replace operations against file contents Fixify fetched itself. Nothing is
executed: syntax checks only parse (json.loads, ast.parse, tree-sitter grammars for
JavaScript / JSX / TypeScript / TSX / CSS, html.parser, delimiter balance as a last resort).
"""

import ast
import json
import posixpath
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from html.parser import HTMLParser

from app.ai.prompts import REDACTED, FixEdit

try:  # tree-sitter: real parsers (C extensions that only build a syntax tree, never execute)
    import tree_sitter_css
    import tree_sitter_javascript
    import tree_sitter_typescript
    from tree_sitter import Language, Parser
except ImportError:  # pragma: no cover - degraded mode: the bracket check is used instead
    Parser = None  # type: ignore[assignment,misc]

_GRAMMARS: dict[str, Callable[[], object]] = (
    {
        "javascript": tree_sitter_javascript.language,  # also parses JSX
        "jsx": tree_sitter_javascript.language,
        "typescript": tree_sitter_typescript.language_typescript,  # no JSX: allows <T>x casts
        "tsx": tree_sitter_typescript.language_tsx,
        "css": tree_sitter_css.language,
    }
    if Parser is not None
    else {}
)

LANGUAGES = {
    ".js": "javascript",
    ".jsx": "jsx",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".vue": "vue",
    ".svelte": "svelte",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".json": "json",
    ".py": "python",
    ".md": "markdown",
    ".mdx": "markdown",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".php": "php",
    ".rb": "ruby",
    ".go": "go",
    ".java": "java",
    ".cs": "csharp",
    ".xml": "xml",
    ".svg": "xml",
    ".astro": "astro",
}
_VOID = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
        "!doctype",
    }
)
_BRACKETED = frozenset(
    {"javascript", "jsx", "typescript", "tsx", "css", "scss", "less", "java", "csharp", "go", "php"}
)
CONTEXT_LINES = 3
MAX_EXCERPT_LINES = 400


def language_for(path: str) -> str:
    return LANGUAGES.get(posixpath.splitext(path)[1].lower(), "text")


@dataclass
class FileChange:
    path: str
    blob_sha: str
    original_text: str
    new_text: str
    edits: list[FixEdit] = field(default_factory=list)


@dataclass
class ValidationReport:
    status: str  # passed | failed | not_available
    messages: list[str]


class EditError(ValueError):
    pass


def apply_edit(text: str, edit: FixEdit) -> str:
    if not edit.original:
        raise EditError(f"{edit.path}: an edit has an empty 'original' snippet.")
    if REDACTED in edit.original or REDACTED in edit.replacement:
        raise EditError(f"{edit.path}: edits may not touch redacted secrets.")
    occurrences = text.count(edit.original)
    if occurrences == 0:
        raise EditError(f"{edit.path}: the original snippet does not appear in the file.")
    if occurrences > 1:
        raise EditError(f"{edit.path}: the original snippet appears {occurrences} times.")
    if edit.original == edit.replacement:
        raise EditError(f"{edit.path}: an edit does not change anything.")
    return text.replace(edit.original, edit.replacement, 1)


def apply_edits(
    files: dict[str, tuple[str, str]], edits: list[FixEdit], max_files: int
) -> tuple[list[FileChange], list[str]]:
    """files: path -> (blob sha, text). Returns the changes and any errors (no partial apply)."""
    errors: list[str] = []
    changes: dict[str, FileChange] = {}
    for edit in edits:
        if edit.path not in files:
            errors.append(f"{edit.path}: this file was not part of the provided context.")
            continue
        sha, original = files[edit.path]
        change = changes.setdefault(edit.path, FileChange(edit.path, sha, original, original))
        try:
            change.new_text = apply_edit(change.new_text, edit)
            change.edits.append(edit)
        except EditError as error:
            errors.append(str(error))
    if len(changes) > max_files:
        errors.append(f"The fix changes {len(changes)} files; at most {max_files} are allowed.")
    if not changes and not errors:
        errors.append("The proposal contains no edits.")
    return list(changes.values()), errors


class _TagBalance(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.problems: list[str] = []

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID:
            return
        if tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass
        else:
            self.problems.append(f"unexpected </{tag}>")


def _html_problems(text: str) -> int:
    parser = _TagBalance()
    parser.feed(text)
    parser.close()
    return len(parser.problems)


def _delimiter_imbalance(text: str) -> int:
    """Approximate: counts (), [], {} outside strings and comments. Used only comparatively."""
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    errors = 0
    i, n = 0, len(text)
    quote: str | None = None
    while i < n:
        char = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if quote:
            if char == "\\":
                i += 2
                continue
            if char == quote:
                quote = None
        elif char in "\"'`":
            quote = char
        elif char == "/" and nxt == "/":
            end = text.find("\n", i)
            i = n if end == -1 else end
            continue
        elif char == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        elif char in "([{":
            stack.append(char)
        elif char in ")]}":
            if stack and stack[-1] == pairs[char]:
                stack.pop()
            else:
                errors += 1
        i += 1
    return errors + len(stack)


@cache
def _parser(language: str) -> "Parser | None":
    grammar = _GRAMMARS.get(language)
    if grammar is None or Parser is None:
        return None
    return Parser(Language(grammar()))


def _parse_errors(language: str, text: str) -> int | None:
    """Number of syntax-error and missing-token nodes, or None if no full parser is available.

    tree-sitter recovers from errors, so the tree is always built; only subtrees that contain
    errors are walked.
    """
    parser = _parser(language)
    if parser is None:
        return None
    root = parser.parse(text.encode("utf-8")).root_node
    if not root.has_error:
        return 0
    errors, stack = 0, [root]
    while stack:
        node = stack.pop()
        if node.is_error or node.is_missing:
            errors += 1
            continue
        stack.extend(child for child in node.children if child.has_error or child.is_missing)
    return errors


def check_syntax(change: FileChange) -> tuple[str, str | None]:
    """(status, message) for one changed file."""
    language = language_for(change.path)
    try:
        if language == "json":
            json.loads(change.new_text)
            return "passed", None
        if language == "python":
            ast.parse(change.new_text, filename=change.path)  # parses; never executes
            return "passed", None
    except (ValueError, SyntaxError) as error:
        return "failed", f"{change.path}: {language} does not parse after the change ({error})."
    if language in ("html", "vue", "svelte", "xml", "astro"):
        before, after = _html_problems(change.original_text), _html_problems(change.new_text)
        if after > before:
            return "failed", f"{change.path}: the change introduces unbalanced markup tags."
        return "passed", None
    after_errors = _parse_errors(language, change.new_text)
    if after_errors is not None:
        before_errors = _parse_errors(language, change.original_text) or 0
        # Comparative, like the other checks: a file that already had syntax the grammar
        # cannot read (or a real error) is not blamed on the change; new errors are.
        if after_errors > before_errors:
            return "failed", f"{change.path}: {language} does not parse after the change."
        if after_errors:
            return "passed", (
                f"{change.path}: the original file already contained {before_errors} "
                f"{language} syntax error(s) the parser could not read; the change adds none."
            )
        return "passed", None
    if language in _BRACKETED:
        before = _delimiter_imbalance(change.original_text)
        after = _delimiter_imbalance(change.new_text)
        if after > before:
            return "failed", f"{change.path}: the change unbalances brackets or braces."
        return "passed", f"{change.path}: basic bracket check only (no full {language} parser)."
    return "not_available", f"{change.path}: no syntax check is available for {language}."


def validate(changes: list[FileChange], edit_errors: list[str]) -> ValidationReport:
    if edit_errors:
        return ValidationReport("failed", edit_errors)
    statuses, messages = [], []
    for change in changes:
        status, message = check_syntax(change)
        statuses.append(status)
        if message:
            messages.append(message)
    if "failed" in statuses:
        return ValidationReport("failed", messages)
    if statuses and all(status == "not_available" for status in statuses):
        return ValidationReport("not_available", messages)
    return ValidationReport("passed", messages)


def excerpt(original: str, new: str, edits: list[FixEdit]) -> tuple[str, str, int]:
    """Smallest line window covering every edit (plus context), before and after."""
    old_lines = original.splitlines(keepends=True)
    first, last = len(old_lines), 0
    for edit in edits:
        index = original.find(edit.original)
        if index == -1:
            continue
        start = original.count("\n", 0, index)
        end = start + edit.original.rstrip("\n").count("\n")
        first, last = min(first, start), max(last, end)
    if first > last:  # nothing located; show the head of the file
        first, last = 0, min(len(old_lines), MAX_EXCERPT_LINES) - 1
    first = max(0, first - CONTEXT_LINES)
    last = min(len(old_lines) - 1, last + CONTEXT_LINES, first + MAX_EXCERPT_LINES)
    before = "".join(old_lines[first : last + 1])
    head = "".join(old_lines[:first])
    tail = "".join(old_lines[last + 1 :])
    after = (
        new[len(head) : len(new) - len(tail)]
        if new.startswith(head) and new.endswith(tail)
        else new
    )
    return before, after, first + 1
