"""Prompts are Markdown files in this context, versioned by the hash of their text.

The version goes into every trace, so a change in answers can be traced back to the
prompt that produced it.
"""

import hashlib
from dataclasses import dataclass
from importlib import resources


@dataclass(frozen=True, slots=True)
class Prompt:
    name: str
    text: str

    @property
    def version(self) -> str:
        return f"{self.name}@{hashlib.sha256(self.text.encode()).hexdigest()[:12]}"

    def fill(self, **values: str) -> str:
        text = self.text
        for key, value in values.items():
            text = text.replace("{" + key + "}", value)
        return text


def load(name: str) -> Prompt:
    files = resources.files("portfolio.contexts.assistant.prompts")
    return Prompt(name, files.joinpath(f"{name}.md").read_text(encoding="utf-8").strip())


# When a flagged answer has too little left after trimming: an honest pointer to Erick.
FALLBACK = {
    "en": (
        "The site doesn't cover that yet. Erick can answer it directly: write through the "
        "contact form or to erickkbonfim@gmail.com."
    ),
    "pt": (
        "O site ainda não fala disso. O Erick pode responder direto: escreva pelo formulário "
        "de contato ou para erickkbonfim@gmail.com."
    ),
}
