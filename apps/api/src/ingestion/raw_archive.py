"""Helper to persist raw provider responses to provider_raw_archive before normalisation."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from apps.api.src.db.models import ProviderRawArchive


def archive_response(
    session: Any,
    provider: str,
    endpoint: str,
    params: dict[str, Any],
    payload_bytes: bytes,
    status_code: int,
) -> ProviderRawArchive:
    """Insert a ProviderRawArchive row and flush (no commit – caller owns the transaction).

    :param session:       SQLAlchemy Session (sync).
    :param provider:      Short provider name, e.g. 'tiingo'.
    :param endpoint:      Full URL that was requested.
    :param params:        Query-param dict (used to compute params_hash).
    :param payload_bytes: Raw response body as bytes.
    :param status_code:   HTTP status code of the response.
    :returns:             The persisted ProviderRawArchive ORM instance.
    """
    canonical_params = json.dumps(params, sort_keys=True)
    params_hash  = hashlib.sha256(canonical_params.encode()).hexdigest()
    content_hash = hashlib.sha256(payload_bytes).hexdigest()

    # Attempt to decode body as UTF-8 text; fall back to base64 representation.
    try:
        payload_text: str | None = payload_bytes.decode("utf-8")
    except UnicodeDecodeError:
        import base64
        payload_text = base64.b64encode(payload_bytes).decode("ascii")

    row = ProviderRawArchive(
        provider=provider,
        endpoint=endpoint,
        params_hash=params_hash,
        content_hash=content_hash,
        status_code=status_code,
        payload_blob=payload_text,
    )
    session.add(row)
    session.flush()
    return row
