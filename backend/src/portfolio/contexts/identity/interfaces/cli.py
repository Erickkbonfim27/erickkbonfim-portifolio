from collections.abc import Callable

from portfolio.contexts.identity.application.use_cases import CreateAdmin
from portfolio.contexts.identity.domain.errors import (
    AdminAlreadyExistsError,
    InvalidEmailError,
    WeakPasswordError,
)

Prompt = Callable[[str], str]


async def create_admin(
    create: CreateAdmin, ask: Prompt, ask_secret: Prompt, say: Callable[[str], None]
) -> int:
    """Interactive `create-admin`. The password is read without echo and asked twice.

    The prompts are injected so the command is testable without a terminal.
    """
    email = ask("Email: ")
    password = ask_secret("Password: ")
    if ask_secret("Repeat password: ") != password:
        say("Passwords do not match.")
        return 1
    try:
        admin = await create(email, password)
    except InvalidEmailError:
        say("Invalid email.")
        return 1
    except WeakPasswordError as weak:
        say(f"Weak password: {weak}.")
        return 1
    except AdminAlreadyExistsError:
        say("An admin with this email already exists.")
        return 1
    say(f"Admin {admin.email} created.")
    return 0
