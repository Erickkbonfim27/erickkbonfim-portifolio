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


# The model says only this for a question that is not about Erick; the site replies.
OFF_TOPIC_MARK = "OFF_TOPIC"

OFF_TOPIC = {
    "en": (
        "That question is outside what I have here: I only know Erick's work. If you like, "
        "I can tell you what he built at Loopia, Vizzion or Rhye."
    ),
    "pt": (
        "Essa pergunta foge do que eu tenho aqui: só conheço o trabalho do Erick. Se quiser, "
        "posso contar o que ele construiu na Loopia, na Vizzion ou na Rhye."
    ),
}


def is_off_topic(reply: str) -> bool:
    """The marker alone, give or take quotes, backticks or a full stop around it."""
    return reply.strip().strip("`'\".[]() \n").upper() == OFF_TOPIC_MARK


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
