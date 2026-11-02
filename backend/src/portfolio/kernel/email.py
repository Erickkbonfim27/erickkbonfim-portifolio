"""Shared kernel: value objects more than one context needs. No I/O, no frameworks."""

import re
from dataclasses import dataclass

# Deliberately loose: one "@", no spaces, a dot in the domain. The goal is to catch
# typos, not to prove deliverability.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_EMAIL_LENGTH = 254


class InvalidEmailError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Email:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "Email":
        normalized = raw.strip().lower()
        if len(normalized) > _MAX_EMAIL_LENGTH or not _EMAIL.match(normalized):
            raise InvalidEmailError(raw)
        return cls(normalized)

    def __str__(self) -> str:
        return self.value
