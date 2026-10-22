"""Opt-in history query router; deliberately has no recording or media backend.

Create and include this router explicitly after managed storage initialization.
It does not open a database, a camera, a socket, or a file on import/construction.
"""

from datetime import datetime, timedelta, timezone
from importlib import metadata
import math
import re
import secrets
from typing import Any, Mapping, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from guardian_history import HISTORY_ID_PATTERN as _ID, validate_event_kind


MAX_QUERY_DAYS = 31
MAX_LIMIT = 200
MAX_OFFSET = 100000
_OMIT = object()
_PRIVATE_KEY = re.compile(r"path|file|token|secret|password|dsn|url|error", re.I)
_FILENAME = re.compile(r"\.(?:mp4|mkv|avi|jpg|jpeg|png|db|sqlite3?|json|py|log)(?:\b|$)", re.I)


def file_response_capability() -> dict:
    """Report installed-version eligibility, never advertise tested HTTP Range.

    Range was introduced in Starlette 0.39.0. This is not an end-to-end or
    security certification: https://starlette.dev/release-notes/#0390-september-23-2024
    Media endpoints remain closed until lease/cleanup and Range tests pass.
    """
    try:
        installed = metadata.version("starlette")
    except metadata.PackageNotFoundError:
        installed = None
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", installed or "")
    eligibility = "unknown"
    if match:
        eligibility = (
            "version_capable_unverified"
            if tuple(map(int, match.groups())) >= (0, 39, 0)
            else "unsupported_version"
        )
    return {
        "starlette_version": installed,
        "file_response_range": eligibility,
        "media_download_enabled": False,
        "resume_verified": False,
    }


def _safe_value(value: Any, token: str, depth: int = 0) -> Any:
    """Conservative public JSON, excluding internal paths and credentials."""
    if depth > 6:
        return _OMIT
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else _OMIT
    if isinstance(value, str):
        # Slash-containing values may be internal relative paths, even when the
        # key does not say 'path'. Do not make private metadata a file index API.
        if "/" in value or "\\" in value or _FILENAME.search(value) or (token and token in value):
            return _OMIT
        return value[:4096]
    if isinstance(value, Mapping):
        result = {}
        for key, item in list(value.items())[:100]:
            if (not isinstance(key, str) or _PRIVATE_KEY.search(key)
                    or "/" in key or "\\" in key or (token and token in key)):
                continue
            cleaned = _safe_value(item, token, depth + 1)
            if cleaned is not _OMIT:
                result[key[:100]] = cleaned
        return result
    if isinstance(value, (tuple, list)):
        result = []
        for item in value[:100]:
            cleaned = _safe_value(item, token, depth + 1)
            if cleaned is not _OMIT:
                result.append(cleaned)
        return result
    return _OMIT


def _utc_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    return datetime.fromtimestamp(float(value), timezone.utc).isoformat().replace("+00:00", "Z")


def _public_row(row: Mapping, event: bool, token: str) -> dict:
    fields = (
        ("id", "kind", "person_id", "payload", "metadata")
        if event else ("id", "size_bytes", "state", "metadata")
    )
    public = {}
    for field in fields:
        if field in row:
            cleaned = _safe_value(row[field], token)
            if cleaned is not _OMIT:
                public[field] = cleaned
    for field in ("started_at", "ended_at"):
        public[field] = _utc_iso(row.get(field))
    return public


def _query(request: Request, events: bool = False) -> dict:
    allowed = {"start", "end", "limit", "offset"}
    if events:
        allowed.add("kind")
    params = request.query_params
    if any(key not in allowed or len(params.getlist(key)) != 1 for key in params):
        raise HTTPException(422, "unsupported_or_duplicate_query_parameter")
    try:
        limit_text, offset_text = params.get("limit", "50"), params.get("offset", "0")
        if (len(limit_text) > 6 or len(offset_text) > 8
                or not limit_text.isdecimal() or not offset_text.isdecimal()):
            raise ValueError
        limit, offset = int(limit_text), int(offset_text)
        if not 1 <= limit <= MAX_LIMIT or not 0 <= offset <= MAX_OFFSET:
            raise ValueError
        times = {}
        for name in ("start", "end"):
            text = params.get(name)
            if text is None:
                times[name] = None
                continue
            if len(text) > 64:
                raise ValueError
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.utcoffset() is None:
                raise ValueError
            times[name] = parsed.timestamp()
        # Complete a one-sided interval so it cannot become an unbounded scan.
        if times["start"] is not None and times["end"] is None:
            times["end"] = times["start"] + timedelta(days=MAX_QUERY_DAYS).total_seconds()
        elif times["end"] is not None and times["start"] is None:
            times["start"] = times["end"] - timedelta(days=MAX_QUERY_DAYS).total_seconds()
        elif times["start"] is None and times["end"] is None:
            times["end"] = datetime.now(timezone.utc).timestamp()
            times["start"] = times["end"] - timedelta(days=MAX_QUERY_DAYS).total_seconds()
        if not 0 < times["end"] - times["start"] <= MAX_QUERY_DAYS * 86400:
            raise ValueError
        result = dict(times, limit=limit, offset=offset)
        if events and params.get("kind") is not None:
            result["kind"] = validate_event_kind(params["kind"])
        return result
    except (ValueError, OverflowError):
        # Never echo input; tokens accidentally supplied as a query value must
        # not appear in error bodies. Credentials belong exclusively in headers.
        raise HTTPException(422, "invalid_history_query") from None


def create_history_router(config: Any, store: Any = None, recorder: Any = None) -> APIRouter:
    """Build the optional router. The caller owns storage and recorder lifecycle.

    Authentication is deliberately explicit across supported FastAPI versions:
    https://fastapi.tiangolo.com/tutorial/security/first-steps/
    Only ``Authorization: Bearer ...`` is accepted; face/admin tokens are unused.
    ``recorder`` is reserved for the future hardware integration, not started here.
    """
    token = getattr(config, "history_token", None) or ""

    def authenticate(request: Request) -> None:
        if not token:
            raise HTTPException(503, "history_token_not_configured")
        authorization = request.headers.get("authorization", "")
        scheme, _, supplied = authorization.partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(
            supplied.encode("utf-8"), token.encode("utf-8")
        ):
            raise HTTPException(401, "invalid_history_credentials", headers={"WWW-Authenticate": "Bearer"})

    router = APIRouter(prefix="/api/history", tags=["history"], dependencies=[Depends(authenticate)])

    def require_store() -> Any:
        if not getattr(config, "enabled", False):
            raise HTTPException(503, "history_disabled")
        if store is None:
            raise HTTPException(503, "history_store_not_initialized")
        return store

    @router.get("/status")
    def status() -> dict:
        enabled = bool(getattr(config, "enabled", False))
        state = "disabled" if not enabled else (
            "prepared" if getattr(config, "encoder", None) else "encoder_not_configured"
        )
        return {
            "state": state,
            "enabled": enabled,
            "store_attached": store is not None,
            "recorder_attached": recorder is not None,
            "capture_integrated": False,
            "recording_backend_ready": False,
            "retention_days": getattr(config, "retention_days", 7),
            **file_response_capability(),
        }

    def query_rows(request: Request, events: bool) -> dict:
        backend = require_store()
        query = _query(request, events)
        try:
            rows = backend.list_events(**query) if events else backend.list_recordings(**query)
            items = [_public_row(row, events, token) for row in rows]
        except Exception:
            # SQLite/filesystem errors can contain SQL or absolute device paths.
            # Do not return or log them from a public endpoint.
            raise HTTPException(503, "history_query_unavailable") from None
        return {"items": items, "limit": query["limit"], "offset": query["offset"]}

    @router.get("/recordings")
    def recordings(request: Request) -> dict:
        return query_rows(request, False)

    @router.get("/events")
    def events(request: Request) -> dict:
        return query_rows(request, True)

    @router.get("/events/{event_id}")
    def event_detail(event_id: str) -> dict:
        backend = require_store()
        if not _ID.fullmatch(event_id):
            raise HTTPException(422, "invalid_event_id")
        try:
            row = backend.get_event(event_id)
            item = _public_row(row, True, token) if row is not None else None
            if item is not None:
                # Additive: an event now lists the clips recorded for that episode.
                lister = getattr(backend, "list_event_recordings", None)
                linked = lister(event_id) if callable(lister) else []
                item["recordings"] = [_public_row(clip, False, token) for clip in linked]
        except Exception:
            raise HTTPException(503, "history_query_unavailable") from None
        if item is None:
            raise HTTPException(404, "history_event_not_found")
        return item

    @router.get("/recordings/{recording_id}/video")
    def video(recording_id: str) -> None:
        require_store()
        if not _ID.fullmatch(recording_id):
            raise HTTPException(422, "invalid_recording_id")
        raise HTTPException(503, "media_not_implemented")

    @router.get("/events/{event_id}/snapshot")
    def snapshot(event_id: str) -> None:
        require_store()
        if not _ID.fullmatch(event_id):
            raise HTTPException(422, "invalid_event_id")
        raise HTTPException(503, "media_not_implemented")

    return router
