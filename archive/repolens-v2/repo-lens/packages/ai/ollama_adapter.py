import os
from typing import Optional, Dict


class OllamaAdapter:
    """Local LLM adapter using Ollama endpoint."""

    def __init__(self, host: Optional[str] = None, model: Optional[str] = None):
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

    def is_available(self) -> bool:
        # Minimal check; real implementation would ping host
        return True

    def generate_answer(self, prompt: str, context: Dict = None) -> str:
        # Return structured placeholder; real integration would POST to /api/generate
        # Example: curl -X POST $OLLAMA_HOST/api/generate -d '{"model":"...","prompt":"..."}'
        return f"[AI analysis based on context] Intent: {context.get('intent', 'unknown') if context else 'unknown'}"
