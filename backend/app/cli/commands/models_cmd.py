"""
`kitehut models` command.
Checks local Ollama status, lists downloaded models, and verifies LLM configuration.
"""

import click

from app.cli.ui import (
    SYM_BULLET,
    bold,
    cyan,
    dim,
    green,
    print_bullet,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
    red,
    yellow,
)
from app.llm.factory import create_llm_provider
from app.llm.ollama_provider import OllamaProvider


@click.command(name="models")
def models_command():
    """Inspect local Ollama AI connection and available LLM models."""
    print_header("Local AI Inference Engine (Ollama)")

    try:
        provider = create_llm_provider()
    except Exception as error:
        print_error(f"Failed to load LLM provider: {error}")
        return

    if not isinstance(provider, OllamaProvider):
        print_info(f"Active Provider: {provider.__class__.__name__}")
        return

    print_bullet(f"Endpoint: {cyan(provider.base_url)}")
    print_bullet(f"Configured Model: {bold(green(provider.model))}")

    if not provider.is_available():
        print_error("Ollama server is NOT running or unreachable at " + provider.base_url)
        print("\n" + bold("Troubleshooting:"))
        print_bullet("1. Install Ollama: https://ollama.com")
        print_bullet("2. Start Ollama: `ollama serve`")
        print_bullet("3. Pull default model: `ollama pull qwen3:4b`")
        return

    print_success("Ollama connection: ONLINE")

    models = provider.list_models()
    print("\n" + bold(f"Available Local Models ({len(models)}):"))
    if not models:
        print_warning("No models found locally. Run `ollama pull qwen3:4b` to install.")
    else:
        for m in models:
            if m == provider.model or m.startswith(provider.model):
                print(f"  {green(SYM_BULLET)} {bold(m)} {green('(active)')}")
            else:
                print(f"  {dim('*')} {m}")
