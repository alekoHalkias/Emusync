"""LLM client: llama-swap HTTP client with retry logic.

Interacts with a local LLM via llama-swap (or any OpenAI-compatible endpoint).
Returns JSON-parsed responses with retry on transient failures.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_TIMEOUT = 300  # 5 minutes for long prompts
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2  # seconds


class LLMClient:
    """HTTP client for llama-swap / OpenAI-compatible endpoints."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = "claude-sonnet-4-20250514",
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _url(self, path: str) -> str:
        """Build a full URL from a path segment."""
        url = f"{self.base_url}{path}"
        if not url.startswith("http"):
            url = f"{self.base_url}/{path.lstrip('/')}"
        return url

    def chat(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Send a chat completion request and return parsed JSON.

        Args:
            system_prompt: System instruction for the model.
            messages: List of {role, content} dicts.
            temperature: Sampling temperature (0.0 for deterministic output).

        Returns:
            Parsed JSON response dict.

        Raises:
            httpx.HTTPError: On persistent failures after retries.
            ValueError: On malformed JSON response.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                *messages,
            ],
            "temperature": temperature,
            "stream": False,
        }

        url = self._url("/v1/chat/completions")
        headers = {"Content-Type": "application/json"}

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug("LLM request (attempt %d): %s", attempt, url)
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(url, headers=headers, json=payload)

                if response.status_code == 429:
                    retry_after = int(response.headers.get("retry-after", self.retry_delay))
                    logger.warning(
                        "Rate limited, waiting %ds (attempt %d/%d)",
                        retry_after, attempt, self.max_retries,
                    )
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.debug("LLM response: %d chars", len(content))
                return self._parse_response(content)

            except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
                logger.warning("LLM request failed (attempt %d/%d): %s", attempt, self.max_retries, e)
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)
                else:
                    raise

        raise httpx.HTTPError(f"LLM request failed after {self.max_retries} attempts")

    def _parse_response(self, content: str) -> dict[str, Any]:
        """Parse the LLM's text response as JSON.

        Handles markdown code fences that the model may wrap around JSON.
        """
        # Strip markdown code fences if present
        stripped = content.strip()
        if stripped.startswith("```"):
            lines = stripped.split("\n")
            # Remove first and last fence lines
            lines = [l for l in lines if not l.strip().startswith("```")]
            stripped = "\n".join(lines).strip()

        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            # Return raw content for downstream error handling
            return {"_raw": content, "_parse_failed": True}

    def health(self) -> bool:
        """Check if the LLM endpoint is reachable."""
        try:
            with httpx.Client(timeout=5) as client:
                resp = client.get(self._url("/v1/models"))
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
