"""Checks an answer must pass before anyone sees it. Code, not a model: cheap and certain.

What can do the most damage in an answer about a person is a fact that is not true:
a number, a company, a technology, a title. So every one of those must appear in the
passages the agent found (or in the question itself). Claims in plain words are left to
the grounding check, which reads them in context.

When an answer still fails after a rewrite, `trim` drops the sentences that carry what
was flagged and keeps the rest: the visitor reads prose, never raw passages.
"""

import json
import re
import unicodedata
from dataclasses import dataclass, field

# Small counts and years read naturally in prose without being claims about the data.
_NUMBER = re.compile(r"(?<![\w\[])(\d+(?:[.,]\d+)*)(?![\w\]])")
_SAFE_MAX = 12
_YEARS = range(1990, 2041)
_YEAR_DIGITS = 4
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_CITATION = re.compile(r"\[(\d{1,2})\]")
# A technology or an organisation written like one: an acronym (AWS, GCP), inner
# capitals (LangGraph, PostGIS) or digits (GPT-4). Ordinary capitalised words (a
# country, a job title) are left to the grounding check, which reads them in context.
_NAME = re.compile(
    r"(?<![\w-])([A-Z]{2,}[\w+#.-]*|[A-Z]?[a-z]+[A-Z][\w+#.-]*|[A-Za-z]+-?\d[\w.-]*)"
)
_COMMON = frozenset(
    {"ok", "ia", "ai", "pt", "en", "url", "faq", "api", "llm", "cto", "ceo", "rh", "hr", "ti"}
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD = re.compile(r"\w{4,}")
# A count in words where the passages give a number: "dozens of sources" for 150.
_VAGUE = re.compile(
    r"\b(dezenas|centenas|milhares|dozens|hundreds|thousands|mais de cem|more than a hundred)\b",
    re.IGNORECASE,
)
MAX_CHARS = 2400
MIN_TRIMMED_CHARS = 60  # less than this left after trimming is not an answer
OVERLAP = 0.6  # share of a flagged claim's words a sentence must contain to carry it


@dataclass(frozen=True, slots=True)
class Verdict:
    passed: bool
    reasons: list[str] = field(default_factory=list)


def _is_year(token: str) -> bool:
    return token.isdigit() and len(token) == _YEAR_DIGITS and int(token) in _YEARS


def _digits(text: str) -> str:
    return text.replace(".", "").replace(",", "")


def ungrounded_numbers(answer: str, sources: str) -> list[str]:
    """Numbers in the answer that the sources do not contain."""
    found = []
    for match in _NUMBER.finditer(_CITATION.sub("", answer)):
        token = match[1]
        plain = _digits(token)
        if plain.isdigit() and int(plain) <= _SAFE_MAX:
            continue
        if _is_year(token) or token in sources or plain in _digits(sources):
            continue
        found.append(token)
    return found


def ungrounded_names(answer: str, sources: str) -> list[str]:
    """Technologies and organisations (AWS, LangGraph, GPT-4) the sources never mention."""
    known = sources.lower()
    found: list[str] = []
    for match in _NAME.finditer(_CITATION.sub("", answer)):
        name = match[1].rstrip(".-")
        # A plural of a known name is known too: "APIs" when the passages say "API".
        singular = name[:-1].lower() if name.endswith("s") else name.lower()
        if {name.lower(), singular} & _COMMON or singular in known or name in found:
            continue
        found.append(name)
    return found


def check(
    answer: str,
    sources: str,
    *,
    passages: int = 0,
    allowed_emails: frozenset[str] = frozenset(),
) -> Verdict:
    """`sources` is what the answer may rely on: the passages' text and the question."""
    reasons = []
    if not answer.strip():
        reasons.append("empty answer")
    if len(answer) > MAX_CHARS:
        reasons.append("answer too long")
    numbers = ungrounded_numbers(answer, sources)
    if numbers:
        reasons.append(f"numbers not in the passages: {', '.join(numbers)}")
    vague = [m[1] for m in _VAGUE.finditer(answer) if m[1].lower() not in sources.lower()]
    if vague:
        reasons.append(f"a vague count instead of the passages' number: {', '.join(vague)}")
    names = ungrounded_names(answer, sources)
    if names:
        reasons.append(f"names not in the passages: {', '.join(names)}")
    cited = {int(n) for n in _CITATION.findall(answer)}
    if any(n < 1 or n > passages for n in cited):
        reasons.append("citations to passages that do not exist")
    # A sentence can end right after an address: "…gmail.com."
    emails = {email.lower().rstrip(".") for email in _EMAIL.findall(answer)} - allowed_emails
    if emails:
        reasons.append("an email address that is not Erick's")
    return Verdict(not reasons, reasons)


def parse_grounding(reply: str) -> list[str] | None:
    """The verifier's list of unsupported claims, or None when its reply is unreadable."""
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(reply[start : end + 1])
    except ValueError:
        return None
    claims = data.get("unsupported") if isinstance(data, dict) else None
    if not isinstance(claims, list):
        return None
    return [str(claim)[:200] for claim in claims if str(claim).strip()]


# What an answer says about the site or about reaching Erick is not a claim about him.
OWNER_EMAIL = "erickkbonfim@gmail.com"
_META = re.compile(
    r"\b(site|portfolio|portfólio|trechos?|passages?)\b.*\b(n[aã]o|not|doesn't|does not|no)\b|"
    r"\b(n[aã]o|not|doesn't|does not|no)\b.*\b(site|portfolio|portfólio|trechos?|passages?)\b|"
    r"formul[aá]rio|contact form|\bcontat|\bcontact|e-?mail|"
    r"pergunt\w* (a|ao|para o)? ?erick|ask erick",
    re.IGNORECASE,
)


def is_meta(claim: str) -> bool:
    """A verifier flags "the site does not detail X" or "write to Erick" now and then; those
    are not facts about Erick. A claim that also names something specific is kept."""
    plain = re.sub(r"[\u2010-\u2015]", "-", claim)  # "e-mail" written with U+2011
    if OWNER_EMAIL in plain.lower():
        return True
    return bool(_META.search(plain)) and not _NUMBER.search(plain) and not _NAME.search(plain)


# Words that carry no fact: a flagged claim is judged by the rest.
_STOP = frozenset(
    [
        "about",
        "also",
        "among",
        "been",
        "being",
        "from",
        "have",
        "into",
        "just",
        "like",
        "more",
        "most",
        "only",
        "over",
        "some",
        "such",
        "than",
        "that",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "very",
        "what",
        "when",
        "where",
        "which",
        "while",
        "with",
        "would",
        "erick",
        "ele",
        "ela",
        "eles",
        "elas",
        "sobre",
        "como",
        "para",
        "pelo",
        "pela",
        "pelos",
        "pelas",
        "entre",
        "também",
        "muito",
        "mais",
        "onde",
        "quando",
        "seus",
        "suas",
        "dele",
        "dela",
        "isso",
        "esse",
        "essa",
        "este",
        "esta",
        "mesmo",
        "ainda",
        "tendo",
        "sendo",
        "foram",
        "foi",
        "era",
        "tem",
        "teve",
        "fez",
        "atuou",
        "trabalhou",
        "serviu",
        "esteve",
        "está",
        "estava",
        "the",
        "and",
        "was",
        "were",
        "has",
        "had",
        "is",
        "are",
        "as",
        "at",
        "in",
        "of",
        "on",
        "for",
        "to",
        "his",
        "her",
        "worked",
        "served",
        "also",
        "its",
        "uma",
        "um",
        "umas",
        "uns",
        "das",
        "dos",
        "nas",
        "nos",
        "currently",
        "atualmente",
        "now",
        "agora",
        "hoje",
        "today",
        "recently",
        "recentemente",
        "tem",
        "experiencia",
        "experience",
        "usou",
        "used",
        "utilizando",
        "using",
        "utiliza",
        "uses",
        "trabalho",
        "work",
        "ja",
        "already",
        "com",
        "sem",
        "por",
        "que",
        "but",
        "who",
        "him",
        "ate",
    ]
)
_MIN_WORD = 3  # keeps CTO, AWS, RAG
_STEM = 5  # "especializado" and "especializa" are the same claim
_PARTS = re.compile(r",|;|\s(?:e|and|mas|but)\s", re.IGNORECASE)
_LINES = re.compile(r"\n|(?<=[.!?])\s+")


def _plain(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in folded if not unicodedata.combining(c))


def _stems(text: str) -> set[str]:
    words = re.findall(r"\w+", _plain(text))
    return {w[:_STEM] for w in words if (len(w) >= _MIN_WORD or w.isdigit()) and w not in _STOP}


def supported(claim: str, sources: str) -> bool:
    """True when the verifier flagged a fact the passages state in other words: each part
    of the claim (split at commas and "and") has all its words in one line of a passage.
    A model judge does that now and then. An invented fact brings a word the site never
    says ("a national award"), and a recombined one ("CTO at Loopia") is not on any line."""
    lines = [_stems(line) for line in _LINES.split(sources) if line.strip()]
    parts = [words for part in _PARTS.split(claim) if (words := _stems(part))]
    return bool(parts) and all(any(words <= line for line in lines) for words in parts)


def _carries(sentence: str, claim: str) -> bool:
    words = {w.lower() for w in _WORD.findall(claim)}
    if not words:
        return False
    found = {w.lower() for w in _WORD.findall(sentence)}
    return len(words & found) / len(words) >= OVERLAP


def trim(
    answer: str,
    sources: str,
    *,
    passages: int,
    unsupported: list[str],
    allowed_emails: frozenset[str] = frozenset(),
) -> str:
    """The answer without the sentences that carry a flagged number, name, citation, email
    or unsupported claim. Empty when too little is left to be an answer."""
    kept = []
    for sentence in filter(str.strip, _SENTENCE.split(answer.strip())):
        cited = [int(n) for n in _CITATION.findall(sentence)]
        emails = {e.lower().rstrip(".") for e in _EMAIL.findall(sentence)} - allowed_emails
        if (
            ungrounded_numbers(sentence, sources)
            or ungrounded_names(sentence, sources)
            or any(n < 1 or n > passages for n in cited)
            or emails
            or any(_carries(sentence, claim) for claim in unsupported)
        ):
            continue
        kept.append(sentence.strip())
    text = " ".join(kept)
    return text if len(text) >= MIN_TRIMMED_CHARS else ""
