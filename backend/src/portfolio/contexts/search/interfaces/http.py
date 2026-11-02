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


def error_response(_: Request, error: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)
