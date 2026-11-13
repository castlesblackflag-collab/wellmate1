"""Loads Sage's persona from persona/sage.md.

Everything above the first `---` line in that file is notes for us; everything below it is
what the model sees. Edit the persona there, not in code.
"""

from functools import lru_cache
from pathlib import Path

PERSONA_PATH = Path(__file__).resolve().parent.parent / "persona" / "sage.md"


def parse_persona(text: str) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "---":
            body = "\n".join(lines[i + 1 :]).strip()
            if body:
                return body
    raise ValueError("persona/sage.md needs a '---' line with the persona text below it")


@lru_cache
def load_persona(path: Path = PERSONA_PATH) -> str:
    return parse_persona(path.read_text(encoding="utf-8"))
