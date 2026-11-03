from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from portfolio.contexts.search.application.use_cases import Search
from portfolio.contexts.search.domain.model import (
    MAX_QUERY_CHARS,
    MAX_RESULTS,
    SearchHit,
    SearchQuery,
)


def _search(request: Request) -> Search:
    return cast(Search, request.app.state.search)


SearchDep = Annotated[Search, Depends(_search)]

router = APIRouter(prefix="/api", tags=["portfolio"])

Kind = Literal[
    "profile", "experience", "project", "education", "certificate", "study", "writing", "post"
]


class HitOut(BaseModel):
    entry_id: UUID
    kind: str
    slug: str
    title: str
    heading: str
    text: str
    score: float

    @classmethod
    def of(cls, hit: SearchHit) -> "HitOut":
        return cls(
            entry_id=hit.entry_id,
            kind=hit.kind,
            slug=hit.slug,
            title=hit.title,
            heading=hit.heading,
            text=hit.text,
            score=hit.score,
        )


@router.get("/search")
async def search(
    search: SearchDep,
    q: Annotated[
        str, Query(min_length=1, max_length=MAX_QUERY_CHARS, description="What to look for")
    ],
    lang: Literal["en", "pt"] = "en",
    limit: Annotated[int, Query(ge=1, le=MAX_RESULTS)] = 5,
    kind: Annotated[list[Kind] | None, Query(description="Only these kinds")] = None,
) -> list[HitOut]:
    """Hybrid search (meaning + exact words) over everything published."""
    query = SearchQuery.build(q, lang, limit, tuple(kind or ()))
    return [HitOut.of(hit) for hit in await search(query)]


class RankedOut(BaseModel):
    slug: str
    title: str
    heading: str
    score: float


class StepOut(BaseModel):
    name: str
    ms: float


class ExplainOut(BaseModel):
    query: str
    hits: list[HitOut]
    dense: list[RankedOut]
    sparse: list[RankedOut]
    steps: list[StepOut]
    degraded: bool


def _ranked(hits: list[SearchHit]) -> list[RankedOut]:
    return [RankedOut(slug=h.slug, title=h.title, heading=h.heading, score=h.score) for h in hits]


@router.get("/search/explain")
async def explain(
    search: SearchDep,
    q: Annotated[
        str, Query(min_length=1, max_length=MAX_QUERY_CHARS, description="What to look for")
    ],
    lang: Literal["en", "pt"] = "en",
    limit: Annotated[int, Query(ge=1, le=MAX_RESULTS)] = 3,
) -> ExplainOut:
    """The same hybrid search, step by step: the dense ranking, the BM25 ranking, the
    fused result and the time each step took. The site's front page shows it live."""
    query = SearchQuery.build(q, lang, limit)
    found = await search.explain(query)
    return ExplainOut(
        query=query.text,
        hits=[HitOut.of(hit) for hit in found.hits],
        dense=_ranked(found.dense),
        sparse=_ranked(found.sparse),
        steps=[StepOut(name=name, ms=ms) for name, ms in found.steps],
        degraded=found.degraded,
    )


def error_response(_: Request, error: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)
