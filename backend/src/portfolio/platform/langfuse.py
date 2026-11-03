"""Langfuse: traces through OpenTelemetry (OTLP/HTTP JSON), datasets and scores through
its public API.

Langfuse v4 stores only what arrives through OTLP; the old /api/public/ingestion
answers 207 and keeps nothing. A trace is a tree of spans; `langfuse.*` attributes
say what each span is (generation, tool, retriever…) and carry input and output.

Traces go out in the background: a request never waits for Langfuse, and when
Langfuse is slow or down the trace is dropped with a warning, never the request.
Datasets and scores are awaited: only the eval run writes them.
"""

import asyncio
import json
import logging
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

log = logging.getLogger(__name__)

OTLP_PATH = "/api/public/otel/v1/traces"
# Scores go in batches through the ingestion API, which keeps taking score events.
INGESTION_PATH = "/api/public/ingestion"
TIMEOUT_SECONDS = 5.0
API_TIMEOUT_SECONDS = 30.0
ATTEMPTS = 3
BATCH = 100
SCOPE = "portfolio"

# (trace id, name, value, comment)
Score = tuple[str, str, float | bool, str | None]


class LangfuseError(Exception):
    pass


def trace_id() -> str:
    """A new OpenTelemetry trace id (32 hex), which Langfuse uses as the trace id."""
    return secrets.token_hex(16)


def span_id() -> str:
    return secrets.token_hex(8)


def root_span_id(trace: str) -> str:
    """The root span of a trace whose id the caller chose: derived, so a score can point
    at the root observation without asking Langfuse for it."""
    return trace[:16]


@dataclass(frozen=True, slots=True)
class Span:
    trace_id: str
    span_id: str
    name: str
    start: datetime
    end: datetime
    attributes: Mapping[str, Any] = field(default_factory=dict)
    parent_id: str | None = None


def _value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, list | tuple) and all(isinstance(item, str) for item in value):
        return {"arrayValue": {"values": [{"stringValue": item} for item in value]}}
    # Input, output and metadata: Langfuse reads them as JSON strings.
    return {"stringValue": json.dumps(value, ensure_ascii=False, default=str)}


def _nanos(moment: datetime) -> str:
    return str(round(moment.timestamp() * 1_000_000) * 1000)


def otlp(spans: Sequence[Span], service: str) -> dict[str, Any]:
    """The OTLP/HTTP JSON body for a batch of spans."""
    return {
        "resourceSpans": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": _value(service)}]},
                "scopeSpans": [
                    {
                        "scope": {"name": SCOPE},
                        "spans": [
                            {
                                "traceId": s.trace_id,
                                "spanId": s.span_id,
                                **({"parentSpanId": s.parent_id} if s.parent_id else {}),
                                "name": s.name,
                                "kind": 1,
                                "startTimeUnixNano": _nanos(s.start),
                                "endTimeUnixNano": _nanos(s.end),
                                "attributes": [
                                    {"key": key, "value": _value(value)}
                                    for key, value in s.attributes.items()
                                    if value is not None
                                ],
                            }
                            for s in spans
                        ],
                    }
                ],
            }
        ]
    }


class Langfuse:
    def __init__(self, http: httpx.AsyncClient, environment: str = "production") -> None:
        self._http = http
        self._environment = environment
        self._pending: set[asyncio.Task[None]] = set()

    @classmethod
    def create(
        cls, host: str, public_key: str, secret_key: str, environment: str = "production"
    ) -> "Langfuse":
        http = httpx.AsyncClient(
            base_url=host.rstrip("/"), auth=(public_key, secret_key), timeout=TIMEOUT_SECONDS
        )
        return cls(http, environment)

    @property
    def environment(self) -> str:
        return self._environment

    def send(self, spans: Sequence[Span]) -> None:
        """Queue one trace's spans and return."""
        tagged = [
            Span(
                s.trace_id,
                s.span_id,
                s.name,
                s.start,
                s.end,
                {**s.attributes, "langfuse.environment": self._environment},
                s.parent_id,
            )
            for s in spans
        ]
        task = asyncio.get_running_loop().create_task(self._post(tagged))
        # A task nobody references can be garbage-collected before it runs.
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _post(self, spans: list[Span]) -> None:
        try:
            response = await self._http.post(OTLP_PATH, json=otlp(spans, SCOPE))
            response.raise_for_status()
        except Exception:
            log.warning("langfuse: trace not sent", exc_info=True)

    async def flush(self) -> None:
        """Wait for the traces already queued."""
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)

    async def close(self) -> None:
        await self.flush()
        await self._http.aclose()

    async def _call(self, method: str, path: str, body: Mapping[str, Any]) -> dict[str, Any]:
        """One API call, tried again when the network or Langfuse fails for a moment."""
        for attempt in range(1, ATTEMPTS + 1):
            try:
                response = await self._http.request(
                    method, path, json=body, timeout=API_TIMEOUT_SECONDS
                )
                if response.status_code < 500 and response.status_code != 429:  # noqa: PLR2004
                    break
            except httpx.TransportError:
                if attempt == ATTEMPTS:
                    raise
            await asyncio.sleep(attempt)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    async def upsert_dataset(self, name: str, description: str, metadata: Mapping[str, Any]) -> str:
        """Returns the dataset's id."""
        found = await self._call(
            "POST",
            "/api/public/v2/datasets",
            {"name": name, "description": description, "metadata": dict(metadata)},
        )
        return str(found.get("id", ""))

    async def upsert_item(
        self,
        dataset: str,
        item_id: str,
        input: Mapping[str, Any],
        expected: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> None:
        """Same id, same item: re-running updates it instead of adding a copy."""
        await self._call(
            "POST",
            "/api/public/dataset-items",
            {
                "datasetName": dataset,
                "id": item_id,
                "input": dict(input),
                "expectedOutput": dict(expected),
                "metadata": dict(metadata),
            },
        )

    async def link_run(
        self, dataset_run: str, item_id: str, trace: str, metadata: Mapping[str, Any]
    ) -> None:
        await self._call(
            "POST",
            "/api/public/dataset-run-items",
            {
                "runName": dataset_run,
                "datasetItemId": item_id,
                "traceId": trace,
                "metadata": dict(metadata),
            },
        )

    async def scores(self, scores: Sequence[Score]) -> None:
        """Every score of a run, a hundred per request."""
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        events = [
            {
                "id": str(uuid4()),
                "timestamp": now,
                "type": "score-create",
                "body": {
                    "id": str(uuid4()),
                    "traceId": trace,
                    "observationId": root_span_id(trace),
                    "name": name,
                    "value": float(value),
                    "dataType": "BOOLEAN" if isinstance(value, bool) else "NUMERIC",
                    "environment": self._environment,
                    **({"comment": comment} if comment else {}),
                },
            }
            for trace, name, value, comment in scores
        ]
        for start in range(0, len(events), BATCH):
            result = await self._call(
                "POST", INGESTION_PATH, {"batch": events[start : start + BATCH]}
            )
            if result.get("errors"):
                raise LangfuseError(f"scores rejected: {str(result['errors'])[:300]}")
