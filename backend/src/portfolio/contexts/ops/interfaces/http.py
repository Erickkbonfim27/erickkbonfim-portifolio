from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/health", tags=["ops"])


class Health(BaseModel):
    status: str


@router.get("/live")
async def live() -> Health:
    """The process is up. Readiness (database, queue, index) arrives with those services."""
    return Health(status="ok")
