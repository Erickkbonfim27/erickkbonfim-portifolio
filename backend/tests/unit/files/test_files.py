import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from botocore.exceptions import ClientError
from httpx import ASGITransport, AsyncClient

from portfolio.contexts.files.application.use_cases import FilesUseCases
from portfolio.contexts.files.domain.model import (
    MAX_SIZE,
    FileInUseError,
    FileTooLargeError,
    MissingFileError,
    UnsupportedFileError,
    clean_filename,
    detect_type,
)
from portfolio.contexts.files.infrastructure.storage import (
    S3Storage,
    content_disposition,
    create_s3_client,
    public_read_policy,
)
from tests.unit.fakes import FakeStorage, FilesStore, files_use_cases
from tests.unit.identity.fakes import FixedClock
from tests.unit.support import World, make_world
from tests.unit.test_http import login

PDF = b"%PDF-1.7\n" + b"x" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 10


class TestDomain:
    @pytest.mark.parametrize(
        ("head", "extension"),
        [
            (PDF, "pdf"),
            (PNG, "png"),
            (b"\xff\xd8\xff\xe0", "jpg"),
            (b"GIF89a....", "gif"),
            (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "webp"),
            (b"PK\x03\x04rest", "zip"),
        ],
    )
    def test_detects_by_magic_bytes(self, head: bytes, extension: str) -> None:
        assert detect_type(head).extension == extension

    @pytest.mark.parametrize("head", [b"<svg onload=alert(1)>", b"MZ\x90\x00", b"<html>"])
    def test_rejects_everything_else(self, head: bytes) -> None:
        with pytest.raises(UnsupportedFileError):
            detect_type(head)

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Currículo Erick.PDF", "Currículo Erick.pdf"),
            ("../../etc/passwd", "passwd.pdf"),
            ("C:\\Users\\e\\cv.exe", "cv.pdf"),
            ("<script>.pdf", "script.pdf"),
            ("...", "file.pdf"),
            ("a   b.pdf", "a b.pdf"),
            ("x" * 300 + ".pdf", "x" * 116 + ".pdf"),
        ],
    )
    def test_clean_filename(self, raw: str, expected: str) -> None:
        assert clean_filename(raw, detect_type(PDF)) == expected


@pytest.fixture
def store() -> FilesStore:
    return FilesStore()


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def uc(store: FilesStore, storage: FakeStorage) -> FilesUseCases:
    return files_use_cases(store, storage, FixedClock())


class TestUseCases:
    async def test_upload_stores_object_and_row(
        self, uc: FilesUseCases, storage: FakeStorage
    ) -> None:
        public = await uc.upload("my cv.pdf", PDF)
        stored = public.file
        assert stored.key == f"{stored.id}.pdf"
        assert (stored.filename, stored.content_type, stored.size) == (
            "my cv.pdf",
            "application/pdf",
            len(PDF),
        )
        assert public.url == f"https://files.test/{stored.key}"
        assert storage.objects[stored.key] == (PDF, "application/pdf", "my cv.pdf")
        assert [f.file.id for f in await uc.list()] == [stored.id]

    async def test_upload_limits(self, uc: FilesUseCases) -> None:
        with pytest.raises(FileTooLargeError):
            await uc.upload("big.pdf", b"%PDF-" + b"x" * MAX_SIZE)
        with pytest.raises(UnsupportedFileError):
            await uc.upload("empty.pdf", b"")

    async def test_failed_row_removes_the_object(
        self, uc: FilesUseCases, store: FilesStore, storage: FakeStorage
    ) -> None:
        store.fail_commit = True
        with pytest.raises(RuntimeError):
            await uc.upload("cv.pdf", PDF)
        assert storage.objects == {}

    async def test_delete(self, uc: FilesUseCases, storage: FakeStorage) -> None:
        stored = (await uc.upload("cv.pdf", PDF)).file
        await uc.delete(stored.id)
        assert storage.objects == {}
        assert await uc.list() == []
        with pytest.raises(MissingFileError):
            await uc.delete(stored.id)

    async def test_delete_refused_while_attached(
        self, uc: FilesUseCases, store: FilesStore, storage: FakeStorage
    ) -> None:
        stored = (await uc.upload("cv.pdf", PDF)).file
        store.in_use.add(stored.id)
        with pytest.raises(FileInUseError):
            await uc.delete(stored.id)
        assert stored.key in storage.objects

    async def test_storage_failure_after_delete_leaves_an_orphan_only(
        self, uc: FilesUseCases, storage: FakeStorage
    ) -> None:
        stored = (await uc.upload("cv.pdf", PDF)).file
        storage.fail_delete = True
        await uc.delete(stored.id)
        assert await uc.list() == []


@pytest.fixture
def world() -> World:
    return make_world()


@pytest.fixture
async def admin(world: World) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(world.app()), base_url="https://a.t") as client:
        await login(client, world)
        yield client


class TestHttp:
    async def test_upload_list_delete(self, admin: AsyncClient) -> None:
        response = await admin.post("/admin/files", files={"file": ("cv.pdf", PDF, "text/plain")})
        assert response.status_code == 201
        body = response.json()
        # The declared text/plain is ignored: the bytes say PDF.
        assert body["content_type"] == "application/pdf"
        assert [f["id"] for f in (await admin.get("/admin/files")).json()] == [body["id"]]
        assert (await admin.delete(f"/admin/files/{body['id']}")).status_code == 204

    async def test_errors(self, admin: AsyncClient, world: World) -> None:
        svg = await admin.post("/admin/files", files={"file": ("a.svg", b"<svg/>", "image/svg")})
        assert svg.status_code == 422
        big = await admin.post(
            "/admin/files", files={"file": ("b.pdf", b"%PDF-" + b"x" * MAX_SIZE, "application/pdf")}
        )
        assert big.status_code == 413
        assert (await admin.delete(f"/admin/files/{uuid4()}")).status_code == 404
        stored = (await admin.post("/admin/files", files={"file": ("c.png", PNG)})).json()
        world.files.in_use.add(UUID(stored["id"]))
        assert (await admin.delete(f"/admin/files/{stored['id']}")).status_code == 409


class FakeS3:
    def __init__(self, bucket_exists: bool = True) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.bucket_exists = bucket_exists

    def put_object(self, **kwargs: Any) -> None:
        self.calls.append(("put_object", kwargs))

    def delete_object(self, **kwargs: Any) -> None:
        self.calls.append(("delete_object", kwargs))

    def head_bucket(self, **kwargs: Any) -> None:
        if not self.bucket_exists:
            raise ClientError({"Error": {"Code": "404"}}, "HeadBucket")

    def create_bucket(self, **kwargs: Any) -> None:
        self.calls.append(("create_bucket", kwargs))

    def put_bucket_policy(self, **kwargs: Any) -> None:
        self.calls.append(("put_bucket_policy", kwargs))


class TestS3Storage:
    async def test_put_sets_download_headers(self) -> None:
        s3 = FakeS3()
        storage = S3Storage(s3, "bucket", "https://files.test")  # type: ignore[arg-type]
        await storage.put("k.pdf", PDF, "application/pdf", "Currículo.pdf")
        await storage.delete("k.pdf")
        (_, put), (_, delete) = s3.calls
        assert put["ContentDisposition"] == (
            "attachment; filename=\"Curr_culo.pdf\"; filename*=UTF-8''Curr%C3%ADculo.pdf"
        )
        assert put["CacheControl"].endswith("immutable")
        assert delete == {"Bucket": "bucket", "Key": "k.pdf"}
        assert storage.public_url("k.pdf") == "https://files.test/k.pdf"

    @pytest.mark.parametrize("exists", [True, False])
    async def test_ensure_bucket(self, exists: bool) -> None:
        s3 = FakeS3(bucket_exists=exists)
        await S3Storage(s3, "bucket", "https://f.t").ensure_bucket()  # type: ignore[arg-type]
        names = [name for name, _ in s3.calls]
        assert names == (
            ["put_bucket_policy"] if exists else ["create_bucket", "put_bucket_policy"]
        )

    def test_policy_allows_get_but_not_list(self) -> None:
        [statement] = json.loads(public_read_policy("b"))["Statement"]
        assert statement["Action"] == ["s3:GetObject"]
        assert statement["Resource"] == ["arn:aws:s3:::b/*"]

    def test_content_disposition_strips_quotes(self) -> None:
        assert content_disposition('a"b.pdf').startswith('attachment; filename="ab.pdf"')

    def test_client_uses_path_style(self) -> None:
        client = create_s3_client("http://minio.test:9000", "k", "s", "us-east-1")
        assert client.meta.endpoint_url == "http://minio.test:9000"
        assert getattr(client.meta.config, "s3") == {"addressing_style": "path"}  # noqa: B009
