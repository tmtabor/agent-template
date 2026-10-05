"""Prompt template loader.

Loads system prompts from .txt files in this directory.
Centralizes prompt loading so all agents use the same pattern.
"""

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent

# Directories searched in order. `examples/__init__.py` appends each example's
# own prompts/ directory so an example runs in place; a copied agent's prompt
# lives in PROMPTS_DIR and needs nothing else.
PROMPTS_DIRS: list[Path] = [PROMPTS_DIR]


def load_prompt(name: str) -> str:
    """Load a prompt template from a .txt file.

    Args:
        name: Filename without extension (e.g., "system" loads "system.txt")

    Returns:
        The prompt text as a string.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """
    for directory in PROMPTS_DIRS:
        prompt_path = directory / f"{name}.txt"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8").strip()
    available = sorted({f.stem for d in PROMPTS_DIRS for f in d.glob("*.txt")})
    raise FileNotFoundError(
        f"Prompt file not found: {name}.txt in {[str(d) for d in PROMPTS_DIRS]}. "
        f"Available prompts: {available}"
    )
