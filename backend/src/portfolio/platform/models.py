"""Imports every ORM model so `Base.metadata` is complete for Alembic and tests."""

import importlib

_MODEL_MODULES = (
    "portfolio.platform.outbox",
    "portfolio.platform.ratelimit",
    "portfolio.platform.jobs",
    "portfolio.contexts.identity.infrastructure.models",
    "portfolio.contexts.files.infrastructure.persistence",
    "portfolio.contexts.content.infrastructure.models",
    "portfolio.contexts.contacts.infrastructure.persistence",
)


def load_all_models() -> None:
    for module in _MODEL_MODULES:
        importlib.import_module(module)
