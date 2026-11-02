from uuid import UUID


class ContentError(Exception):
    """Base class for every content rule violation."""


class InvalidRichTextError(ContentError):
    pass


class InvalidEntryError(ContentError):
    pass


class EntryNotFoundError(ContentError):
    def __init__(self, entry_id: UUID) -> None:
        super().__init__(f"entry {entry_id} not found")
        self.entry_id = entry_id


class NoSuchEntryError(ContentError):
    """No published entry of this kind has this slug."""

    def __init__(self, kind: str, slug: str) -> None:
        super().__init__(f"no published {kind} {slug!r}")


class SlugTakenError(ContentError):
    pass


class SingletonKindError(ContentError):
    """A kind that allows a single entry (the profile) already has one."""


class VersionConflictError(ContentError):
    """The entry changed since the client loaded it."""

    def __init__(self, current: int) -> None:
        super().__init__(f"entry is at version {current}")
        self.current = current


class IncompleteEntryError(ContentError):
    """Publishing needs every language filled in."""


class UnknownSkillError(ContentError):
    pass


class UnknownFileError(ContentError):
    pass
