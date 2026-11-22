"""Request and validate structured Gemini output."""

import logging
from time import monotonic
from typing import TypeVar

import httpx
from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import AiUnavailableError

Result = TypeVar("Result", bound=BaseModel)
logger = logging.getLogger("uvicorn.error.talentfinder.gemini")


def generate_json(
    schema: type[Result], prompt: str, document: dict, failure_message: str
) -> Result:
    key = settings.gemini_api_key
    if not settings.ai_enabled or key is None:
        logger.warning("Gemini unavailable operation=%s reason=missing_key", schema.__name__)
        raise AiUnavailableError(failure_message)
    model = settings.gemini_model.removeprefix("models/")
    operation = schema.__name__
    started = monotonic()
    logger.info("Gemini request started operation=%s model=%s", operation, model)

    try:
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": key.get_secret_value().strip()},
            json={
                "systemInstruction": {"parts": [{"text": prompt}]},
                "contents": [{"parts": [document]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseJsonSchema": schema.model_json_schema(),
                },
            },
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
        response.raise_for_status()
        logger.info(
            "Gemini response received operation=%s status=%d elapsed=%.2fs",
            operation, response.status_code, monotonic() - started,
        )
        candidate = response.json()["candidates"][0]
        if candidate.get("finishReason") != "STOP":
            raise ValueError("Incomplete Gemini response")
        parts = candidate["content"]["parts"]
        result = "".join(part.get("text", "") for part in parts if not part.get("thought"))
        parsed = schema.model_validate_json(result)
    except httpx.HTTPStatusError as error:
        code = error.response.status_code
        logger.warning(
            "Gemini rejected request operation=%s status=%d elapsed=%.2fs",
            operation, code, monotonic() - started,
        )
        if code == 429:
            raise AiUnavailableError("Gemini rate limit reached. Try again shortly.") from None
        if code == 503:
            raise AiUnavailableError("Gemini is unavailable. Try again shortly.") from None
    except httpx.RequestError as error:
        logger.warning(
            "Gemini transport failure operation=%s error=%s elapsed=%.2fs",
            operation, type(error).__name__, monotonic() - started,
        )
        if isinstance(error, httpx.TimeoutException):
            raise AiUnavailableError("Gemini timed out. Try again or continue manually.") from None
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
        logger.warning(
            "Gemini output validation failed operation=%s error=%s",
            operation, type(error).__name__,
        )
    else:
        logger.info("Gemini output validated operation=%s", operation)
        return parsed

    raise AiUnavailableError(failure_message)
