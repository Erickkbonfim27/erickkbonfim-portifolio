"""Which path a question takes, decided by rules, without a model call."""

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class Mode(StrEnum):
    DIRECT = "direct"  # small talk: answer without looking anything up
    TOOLS = "tools"  # look things up, then answer


@dataclass(frozen=True, slots=True)
class Route:
    mode: Mode
    reason: str


_GREETING = (
    r"(oi+|ola+|e ai|hey|hi+|hello|bom dia|boa tarde|boa noite|good (morning|afternoon|evening)|"
    r"obrigad[oa]|muito obrigad[oa]|valeu|thanks?( you)?|thank you|tudo bem|tudo bom|"
    r"como vai|how are you|ok(ay)?|tchau|bye)"
)
# One greeting or a few in a row: "Oi, tudo bem?", "hi! how are you?".
_SMALL_TALK = re.compile(rf"^{_GREETING}([,!.? ]+{_GREETING})*[!.? ]*$")


def _plain(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in folded if not unicodedata.combining(char)).strip()


def route(question: str) -> Route:
    if _SMALL_TALK.match(_plain(question)):
        return Route(Mode.DIRECT, "small talk")
    return Route(Mode.TOOLS, "a question about the work")
