import json
from typing import Any

import httpx
import pytest

from portfolio.contexts.search.infrastructure import openrouter
from portfolio.contexts.search.infrastructure.openrouter import EmbeddingError, OpenRouterDense


class Provider:
    """OpenRouter's embeddings endpoint, answering with vectors made from each input."""

    def __init__(self, dimension: int = 3) -> None:
        self.dimension = dimension
        self.requests: list[dict[str, Any]] = []
        self.timeouts: list[float] = []
        self.reply: Any = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        self.timeouts.append(request.extensions["timeout"]["read"])
        if self.reply is not None:
            return self.reply  # type: ignore[no-any-return]
        data = [
            {"object": "embedding", "index": i, "embedding": [float(len(text))] * self.dimension}
            for i, text in enumerate(body["input"])
        ]
        # Out of order on purpose: the index field, not the position, says which is which.
        return httpx.Response(200, json={"object": "list", "data": data[::-1]})


def dense(provider: Provider, dimension: int = 3) -> OpenRouterDense:
    http = httpx.AsyncClient(transport=httpx.MockTransport(provider), base_url="https://or.test")
    return OpenRouterDense(http, "openai/text-embedding-3-small", dimension)


async def test_documents_in_batches_and_in_order() -> None:
    provider = Provider()
    texts = ["x" * (i % 7 + 1) for i in range(openrouter.BATCH_SIZE * 2 + 2)]
    vectors = await dense(provider).documents(texts)
    assert vectors == [[float(len(t))] * 3 for t in texts]
    assert [len(r["input"]) for r in provider.requests] == [64, 64, 2]
    assert provider.requests[0] | {"input": None} == {
        "model": "openai/text-embedding-3-small",
        "input": None,
        "dimensions": 3,
        "encoding_format": "float",
    }
    assert provider.timeouts[0] == openrouter.DOCUMENTS_TIMEOUT_SECONDS


async def test_no_documents_no_request() -> None:
    provider = Provider()
    assert await dense(provider).documents([]) == []
    assert provider.requests == []


async def test_query_gives_up_fast() -> None:
    provider = Provider()
    assert await dense(provider).query("abcd") == [4.0, 4.0, 4.0]
    assert provider.timeouts == [openrouter.QUERY_TIMEOUT_SECONDS]


async def test_http_errors_propagate() -> None:
    provider = Provider()
    provider.reply = httpx.Response(401, json={"error": {"message": "No auth"}})
    with pytest.raises(httpx.HTTPStatusError):
        await dense(provider).query("q")


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        ({"error": {"message": "No endpoints found"}}, "No endpoints found"),
        ({"object": "list"}, "no embeddings returned"),
        ({"data": []}, "asked for 1 embeddings, got 0"),
        ({"data": [{"index": 0, "embedding": [1.0, 2.0]}]}, "did not return 3 dimensions"),
    ],
)
async def test_unusable_answers_are_errors(reply: dict[str, Any], reason: str) -> None:
    provider = Provider()
    provider.reply = httpx.Response(200, json=reply)
    with pytest.raises(EmbeddingError, match=reason):
        await dense(provider).query("q")


async def test_factory_authenticates_and_closes() -> None:
    encoder = OpenRouterDense.create("sk-or-key", "openai/text-embedding-3-small", 1536)
    http = encoder._http
    assert encoder.dimension == 1536
    assert http.headers["authorization"] == "Bearer sk-or-key"
    assert str(http.base_url) == "https://openrouter.ai/api/v1/"
    await encoder.close()
    assert http.is_closed
