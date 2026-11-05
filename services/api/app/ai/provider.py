"""AI provider abstraction.

Fixify talks to models only through `AIProvider.generate_json`: one request, one schema-checked
JSON object back. The provider is chosen by AI_PROVIDER; with "none" (or no API key) there is no
provider and callers report AI as unavailable instead of producing anything synthetic.
New providers implement the same protocol.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)

# Models that accept the server-side refusal fallback in its "default" form.
_FALLBACK_MODELS = frozenset(
    {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
)
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass(frozen=True)
class AIResult:
    data: dict[str, Any]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


class AIError(Exception):
    """Safe to show: `public_message` never contains provider internals or secrets."""

    def __init__(self, public_message: str, *, retryable: bool) -> None:
        super().__init__(public_message)
        self.public_message = public_message
        self.retryable = retryable


class AIUnavailableError(AIError):
    def __init__(self) -> None:
        super().__init__(
            "AI analysis is not configured on this server (AI_PROVIDER / ANTHROPIC_API_KEY).",
            retryable=False,
        )


class AIProvider(Protocol):
    name: str
    model: str

    async def generate_json(
        self, *, system: str, user_content: str, schema: dict[str, Any], max_tokens: int
    ) -> AIResult: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, config: Settings) -> None:
        self.model = config.ai_model
        self._effort = config.ai_effort
        self._fallback = config.ai_refusal_fallback and config.ai_model in _FALLBACK_MODELS
        self._client = anthropic.AsyncAnthropic(
            api_key=config.anthropic_api_key.get_secret_value(),
            timeout=float(config.ai_timeout_seconds),
            max_retries=config.ai_max_retries,  # SDK retries 408/409/429/5xx and connection errors
        )

    async def generate_json(
        self, *, system: str, user_content: str, schema: dict[str, Any], max_tokens: int
    ) -> AIResult:
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user_content}],
            "output_config": {
                "effort": self._effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        }
        if self._fallback:
            request["betas"] = [_FALLBACK_BETA]
            request["fallbacks"] = "default"
        try:
            response = await self._client.beta.messages.create(**request)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as error:
            logger.error("AI provider rejected credentials (request id %s)", _request_id(error))
            raise AIError(
                "The AI provider rejected the configured API key.", retryable=False
            ) from error
        except anthropic.NotFoundError as error:
            raise AIError(
                f"The AI model {self.model!r} is not available.", retryable=False
            ) from error
        except anthropic.BadRequestError as error:
            logger.error(
                "AI request rejected: %s (request id %s)", error.message, _request_id(error)
            )
            raise AIError("The AI provider rejected the request.", retryable=False) from error
        except anthropic.RateLimitError as error:
            raise AIError("The AI provider is rate limiting requests.", retryable=True) from error
        except anthropic.APIStatusError as error:
            retryable = error.status_code >= 500
            logger.warning(
                "AI provider error %s (request id %s)", error.status_code, _request_id(error)
            )
            raise AIError("The AI provider returned an error.", retryable=retryable) from error
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as error:
            raise AIError(
                "The AI provider could not be reached in time.", retryable=True
            ) from error

        if response.stop_reason == "refusal":
            raise AIError("The AI model declined to analyze this content.", retryable=False)
        if response.stop_reason == "max_tokens":
            raise AIError("The AI response exceeded the output limit.", retryable=False)
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            raise AIError("The AI provider returned no answer.", retryable=True)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise AIError("The AI provider returned malformed output.", retryable=True) from error
        if not isinstance(data, dict):
            raise AIError("The AI provider returned malformed output.", retryable=True)
        usage = response.usage
        return AIResult(
            data=data,
            provider=self.name,
            model=response.model,
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        )


def _request_id(error: anthropic.APIStatusError) -> str:
    return error.response.headers.get("request-id", "unknown") if error.response else "unknown"


_provider: AIProvider | None = None


def create_ai_provider(config: Settings = settings) -> AIProvider | None:
    if not config.ai_configured:
        return None
    return AnthropicProvider(config)


def get_ai_provider() -> AIProvider | None:
    """Shared provider (one HTTP connection pool). None means AI is unavailable."""
    global _provider
    if _provider is None:
        _provider = create_ai_provider()
    return _provider


def ai_status(config: Settings = settings) -> dict[str, Any]:
    return {
        "available": config.ai_configured,
        "provider": config.ai_provider if config.ai_configured else None,
        "model": config.ai_model if config.ai_configured else None,
    }
