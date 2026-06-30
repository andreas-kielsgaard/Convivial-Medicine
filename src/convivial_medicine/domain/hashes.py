from __future__ import annotations

import re
from hashlib import sha256

_SHA256_URI_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def sha256_hex(data: bytes) -> str:
    return sha256(data).hexdigest()


def sha256_uri(data: bytes) -> str:
    return f"sha256:{sha256_hex(data)}"


def is_sha256_uri(value: str) -> bool:
    return _SHA256_URI_PATTERN.fullmatch(value) is not None


def validate_sha256_uri(value: str) -> str:
    if not is_sha256_uri(value):
        raise ValueError("expected canonical sha256:<64 lowercase hex> hash")
    return value
