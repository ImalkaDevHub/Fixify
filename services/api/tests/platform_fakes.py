"""Test doubles for the AI provider and the GitHub API (no network, no real credentials)."""

import base64
import hashlib
import json
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from app.ai.provider import AIError, AIResult

INDEX_HTML = (
    '<!doctype html>\n<html>\n  <head>\n    <meta charset="utf-8">\n  </head>\n'
    "  <body>\n    <h1>Welcome</h1>\n  </body>\n</html>\n"
)
APP_JS = "function start() {\n  console.log('ready');\n}\nstart();\n"


class FakeProvider:
    """Returns scripted JSON objects (or raises scripted errors) and records every request."""

    name = "fake"
    model = "fake-model"

    def __init__(self, *responses: dict[str, Any] | AIError) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def generate_json(self, *, system, user_content, schema, max_tokens) -> AIResult:
        self.calls.append({"system": system, "user_content": user_content, "schema": schema})
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, AIError):
            raise response
        return AIResult(
            data=response, provider="fake", model="fake-model", input_tokens=100, output_tokens=50
        )


def analysis_output(**overrides: Any) -> dict[str, Any]:
    data = {
        "summary": "The page has no title.",
        "technical_explanation": "document.title is empty.",
        "root_cause": "The <head> of index.html lacks a <title> element.",
        "user_impact": "Tabs and bookmarks show the URL instead of a name.",
        "why_it_matters": "Titles identify the page for people and search engines.",
        "recommended_solution": "Add <title>Site</title> to index.html.",
        "fix_complexity": "trivial",
        "confidence": "high",
        "suggested_locations": [
            {"path": "index.html", "reason": "Contains the document head."},
            {"path": "invented/secret.py", "reason": "Not a real file."},
        ],
        "evidence_refs": ["title"],
        "related_finding_ids": ["not-a-real-id"],
    }
    data.update(overrides)
    return data


def fix_output(**overrides: Any) -> dict[str, Any]:
    data = {
        "title": "Add a page title",
        "explanation": "Adds a <title> element to the document head.",
        "impact": "None beyond the visible tab title.",
        "confidence": "high",
        "edits": [
            {
                "path": "index.html",
                "original": '    <meta charset="utf-8">\n',
                "replacement": '    <meta charset="utf-8">\n    <title>Example site</title>\n',
                "reason": "Pages need a title.",
            }
        ],
        "cannot_fix_reason": "",
    }
    data.update(overrides)
    return data


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


class FakeGitHub:
    """Just enough of GitHub's REST API, served through httpx.MockTransport."""

    TOKEN = "gho_" + "t" * 36

    def __init__(self) -> None:
        self.files: dict[str, str] = {
            "index.html": INDEX_HTML,
            "src/app.js": APP_JS,
            ".env": "SECRET_KEY=do-not-read\n",
            "node_modules/lib/index.js": "module.exports = 1;\n",
        }
        self.head = "c0ffee" * 6 + "abcd"
        self.revoked = False
        self.refs: dict[str, str] = {}
        self.pulls: list[dict[str, Any]] = []
        self.writes: list[tuple[str, str]] = []
        self.blobs: dict[str, str] = {}
        self.authorization_headers: set[str] = set()
        self.revoked_grants = 0

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def _json(self, data: Any, status: int = 200, headers: dict[str, str] | None = None):
        return httpx.Response(status, json=data, headers=headers or {})

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = urlsplit(str(request.url))
        path, query = url.path, parse_qs(url.query)
        if path == "/login/oauth/access_token":  # any GitHub web host (incl. Enterprise)
            form = parse_qs(request.content.decode())
            if form.get("code") == ["good-code"]:
                return self._json({"access_token": self.TOKEN, "scope": "repo"})
            return self._json({"error": "bad_verification_code"})
        if request.method == "DELETE" and path.startswith("/applications/"):
            self.revoked_grants += 1
            return httpx.Response(204)
        self.authorization_headers.add(request.headers.get("authorization", ""))
        if self.revoked:
            return self._json({"message": "Bad credentials"}, 401)
        repo = "/repos/octo/site"
        if path == "/user":
            return self._json(
                {"id": 42, "login": "octo", "avatar_url": "https://a/x.png"},
                headers={"x-oauth-scopes": "repo"},
            )
        if path == "/user/repos":
            return self._json([self._repo()])
        if path == repo:
            return self._json(self._repo())
        if path == f"{repo}/branches":
            return self._json([{"name": "main"}, {"name": "dev"}])
        if path.startswith(f"{repo}/git/ref/heads/"):
            branch = path.removeprefix(f"{repo}/git/ref/heads/")
            sha = self.head if branch in ("main", "dev") else self.refs.get(branch)
            if sha is None:
                return self._json({"message": "Not Found"}, 404)
            return self._json({"object": {"sha": sha}})
        if path.startswith(f"{repo}/git/trees/") and request.method == "GET":
            return self._json(
                {
                    "tree": [
                        {
                            "path": p,
                            "type": "blob",
                            "sha": _sha(t),
                            "size": len(t.encode()),
                            "mode": "100644",
                        }
                        for p, t in self.files.items()
                    ],
                    "truncated": False,
                }
            )
        if path.startswith(f"{repo}/git/blobs/") and request.method == "GET":
            sha = path.rsplit("/", 1)[-1]
            for text in self.files.values():
                if _sha(text) == sha:
                    return self._json(
                        {"encoding": "base64", "content": base64.b64encode(text.encode()).decode()}
                    )
            return self._json({"message": "Not Found"}, 404)
        if path.startswith(f"{repo}/git/commits/") and request.method == "GET":
            return self._json({"tree": {"sha": "tree-" + path.rsplit("/", 1)[-1][:8]}})
        body = json.loads(request.content or b"{}")
        if request.method == "POST" and path == f"{repo}/git/blobs":
            sha = _sha(body["content"])
            self.blobs[sha] = body["content"]
            self.writes.append(("blob", sha))
            return self._json({"sha": sha}, 201)
        if request.method == "POST" and path == f"{repo}/git/trees":
            self.writes.append(("tree", json.dumps(body["tree"])))
            return self._json({"sha": "newtree"}, 201)
        if request.method == "POST" and path == f"{repo}/git/commits":
            self.writes.append(("commit", body["message"]))
            return self._json({"sha": "newcommit"}, 201)
        if request.method == "POST" and path == f"{repo}/git/refs":
            branch = body["ref"].removeprefix("refs/heads/")
            self.refs[branch] = body["sha"]
            self.writes.append(("ref", branch))
            return self._json({"ref": body["ref"]}, 201)
        if path == f"{repo}/pulls" and request.method == "GET":
            head = query.get("head", [""])[0].split(":", 1)[-1]
            return self._json([p for p in self.pulls if p["head"] == head][:1])
        if path == f"{repo}/pulls" and request.method == "POST":
            pull = {
                "number": len(self.pulls) + 1,
                "html_url": "https://github.com/octo/site/pull/1",
                "state": "open",
                "head": body["head"],
                "base": body["base"],
                "title": body["title"],
                "body": body["body"],
                "merged_at": None,
            }
            self.pulls.append(pull)
            self.writes.append(("pull", body["title"]))
            return self._json(pull, 201)
        if path.startswith(f"{repo}/pulls/"):
            number = int(path.rsplit("/", 1)[-1])
            return self._json(self.pulls[number - 1])
        return self._json({"message": f"unhandled {request.method} {path}"}, 404)

    @staticmethod
    def _repo() -> dict[str, Any]:
        return {
            "id": 7,
            "full_name": "octo/site",
            "private": False,
            "default_branch": "main",
            "description": "Demo",
            "html_url": "https://github.com/octo/site",
            "permissions": {"push": True},
            "updated_at": "2026-01-01T00:00:00Z",
        }
