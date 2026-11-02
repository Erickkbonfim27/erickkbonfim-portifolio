from enum import StrEnum


class Kind(StrEnum):
    PROFILE = "profile"
    EXPERIENCE = "experience"
    PROJECT = "project"
    EDUCATION = "education"
    CERTIFICATE = "certificate"
    STUDY = "study"
    WRITING = "writing"
    POST = "post"
    SKILL = "skill"


# Kinds that may have at most one entry.
SINGLETON_KINDS = frozenset({Kind.PROFILE})


class Status(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class Lang(StrEnum):
    EN = "en"
    PT = "pt"
