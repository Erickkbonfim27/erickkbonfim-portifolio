from collections.abc import Iterator

import pytest

from portfolio import cli
from portfolio.contexts.files.infrastructure.storage import S3Storage
from portfolio.contexts.identity.interfaces import cli as identity_cli
from tests.unit.files.test_files import FakeS3
from tests.unit.identity.fakes import Harness, make_harness
from tests.unit.support import REQUIRED_SETTINGS, make_world

EMAIL = "erick@example.dev"
PASSWORD = "correct horse battery staple"


def _answers(*values: str) -> "Iterator[str]":
    return iter(values)


async def _run(h: Harness, email: str, *secrets: str) -> tuple[int, list[str]]:
    said: list[str] = []
    pending = _answers(*secrets)
    code = await identity_cli.create_admin(
        h.use_cases.create_admin,
        ask=lambda _prompt: email,
        ask_secret=lambda _prompt: next(pending),
        say=said.append,
    )
    return code, said


@pytest.fixture
def h() -> Harness:
    return make_harness()


async def test_creates_the_admin(h: Harness) -> None:
    code, said = await _run(h, EMAIL, PASSWORD, PASSWORD)
    assert code == 0
    assert said == [f"Admin {EMAIL} created."]


@pytest.mark.parametrize(
    ("email", "secrets", "message"),
    [
        (EMAIL, (PASSWORD, "different password"), "Passwords do not match."),
        ("not-an-email", (PASSWORD, PASSWORD), "Invalid email."),
        (EMAIL, ("short", "short"), "Weak password: password must have at least 12 characters."),
    ],
)
async def test_rejects(h: Harness, email: str, secrets: tuple[str, str], message: str) -> None:
    code, said = await _run(h, email, *secrets)
    assert (code, said) == (1, [message])
    assert h.store.admins == {}


async def test_rejects_a_second_admin_with_the_same_email(h: Harness) -> None:
    await _run(h, EMAIL, PASSWORD, PASSWORD)
    code, said = await _run(h, EMAIL, PASSWORD, PASSWORD)
    assert (code, said) == (1, ["An admin with this email already exists."])


def test_main_wires_terminal_prompts_and_closes_the_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt: EMAIL)
    monkeypatch.setattr("getpass.getpass", lambda _prompt: PASSWORD)
    world = make_world()
    assert cli.main(["create-admin"], world.container()) == 0
    assert world.closer.closed
    assert len(world.identity.store.admins) == 1


def test_main_requires_a_command() -> None:
    with pytest.raises(SystemExit):
        cli.main([])


def test_worker_command_runs_the_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[object] = []

    async def fake_run_worker(settings: object) -> None:
        started.append(settings)

    monkeypatch.setattr("portfolio.worker.run_worker", fake_run_worker)
    for name, value in REQUIRED_SETTINGS.items():
        monkeypatch.setenv(name.upper(), str(value))
    assert cli.main(["worker"]) == 0
    assert len(started) == 1


def test_setup_storage_applies_the_policy(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    s3 = FakeS3(bucket_exists=False)

    class Engine:
        disposed = False

        async def dispose(self) -> None:
            Engine.disposed = True

    class Closeable:
        async def close(self) -> None:
            return None

    class Infra:
        storage = S3Storage(s3, "portfolio", "https://files.test")  # type: ignore[arg-type]
        engine = Engine()
        qdrant = Closeable()
        dense = Closeable()

    monkeypatch.setattr(cli, "build_infrastructure", lambda _settings: Infra())
    for name, value in REQUIRED_SETTINGS.items():
        monkeypatch.setenv(name.upper(), str(value))
    assert cli.main(["setup-storage"]) == 0
    assert [call for call, _ in s3.calls] == ["create_bucket", "put_bucket_policy"]
    assert Engine.disposed
    assert "public read, no listing" in capsys.readouterr().out


def test_reindex_rebuilds_from_published_content(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    closed: list[bool] = []

    class Reindex:
        async def __call__(self) -> int:
            return 42

    class SearchUseCases:
        reindex = Reindex()

    async def fake_close(_infra: object) -> None:
        closed.append(True)

    monkeypatch.setattr(cli, "build_infrastructure", lambda _settings: object())
    monkeypatch.setattr(cli, "search_use_cases", lambda _infra: SearchUseCases())
    monkeypatch.setattr(cli, "close_infrastructure", fake_close)
    for name, value in REQUIRED_SETTINGS.items():
        monkeypatch.setenv(name.upper(), str(value))
    assert cli.main(["reindex"]) == 0
    assert closed == [True]
    assert "Index rebuilt: 42 chunks." in capsys.readouterr().out
