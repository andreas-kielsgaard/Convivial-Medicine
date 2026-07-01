from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from convivial_medicine.domain.canonical_json import canonical_json_bytes
from convivial_medicine.domain.hashes import sha256_uri

SECRET_PARAM_NAMES = frozenset({"api_key"})


def public_request_params(params: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value for key, value in sorted(params.items()) if key.lower() not in SECRET_PARAM_NAMES
    }


def redacted_request_params(params: Mapping[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in sorted(params.items()):
        redacted[key] = "<redacted>" if key.lower() in SECRET_PARAM_NAMES else value
    return redacted


def request_fingerprint_payload(
    *,
    method: str,
    endpoint: str,
    params: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "method": method.upper(),
        "endpoint": endpoint,
        "params": public_request_params(params),
    }


def request_fingerprint(
    *,
    method: str,
    endpoint: str,
    params: Mapping[str, str],
) -> str:
    return sha256_uri(
        canonical_json_bytes(
            request_fingerprint_payload(method=method, endpoint=endpoint, params=params)
        )
    )
