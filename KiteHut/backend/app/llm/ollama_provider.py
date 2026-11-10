"""
Ollama LLM Provider.

Connects to a local Ollama server for zero-cost AI inference.
Default model: qwen3:4b (configurable via environment).
"""

import json
import os
import urllib.request
import urllib.error

from app.llm.base import BaseLLMProvider, LLMProviderError


# Default configuration
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3:4b"
DEFAULT_TIMEOUT = 120  # seconds


class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM provider."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ):
        self.base_url = (
            base_url
            or os.getenv("OLLAMA_BASE_URL", DEFAULT_BASE_URL)
        )
        self.model = (
            model
            or os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
        )
        self.timeout = timeout or DEFAULT_TIMEOUT

    def _chat(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        """Send a chat completion request to Ollama."""

        messages = []

        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt,
            })

        messages.append({
            "role": "user",
            "content": prompt,
        })

        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 4096,
            },
        }).encode("utf-8")

        url = f"{self.base_url}/api/chat"

        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(
                req, timeout=self.timeout
            ) as response:
                data = json.loads(response.read().decode("utf-8"))

            return data["message"]["content"]

        except urllib.error.URLError as error:
            raise LLMProviderError(
                f"Cannot connect to Ollama at {self.base_url}. "
                f"Is Ollama running? Error: {error}"
            )

        except (KeyError, json.JSONDecodeError) as error:
            raise LLMProviderError(
                f"Invalid response from Ollama: {error}"
            )

        except Exception as error:
            raise LLMProviderError(
                f"Ollama request failed: {error}"
            )

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        """
        Generate a response from Ollama.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system instructions.

        Returns:
            The model's text response.
        """

        return self._chat(prompt, system_prompt)

    def is_available(self) -> bool:
        """Check if Ollama is reachable."""

        try:
            url = f"{self.base_url}/api/tags"
            req = urllib.request.urlopen(url, timeout=0.5)
            req.read()
            return True

        except Exception:
            return False

    def list_models(self) -> list[str]:
        """List available models on the Ollama server."""

        try:
            url = f"{self.base_url}/api/tags"
            req = urllib.request.urlopen(url, timeout=5)
            data = json.loads(req.read().decode("utf-8"))
            return [
                m["name"]
                for m in data.get("models", [])
            ]

        except Exception:
            return []
