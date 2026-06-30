from __future__ import annotations

import json
import math

type JsonScalar = None | bool | int | float | str
type CanonicalJsonValue = JsonScalar | list[CanonicalJsonValue] | dict[str, CanonicalJsonValue]


def canonical_json_bytes(value: object) -> bytes:
    """Serialize the project's deterministic JSON subset to UTF-8 bytes.

    This is not a full RFC 8785/JCS implementation. It is a project-level
    canonical subset for hashes: string object keys, sorted keys, no
    insignificant whitespace, UTF-8 output, and finite JSON scalar values.
    """
    _validate_canonical_json(value, "$")
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_json_text(value: object) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def _validate_canonical_json(value: object, path: str) -> None:
    if value is None or isinstance(value, str | bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must be a finite JSON number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_canonical_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} object keys must be strings")
            _validate_canonical_json(item, f"{path}.{key}")
        return
    raise TypeError(f"{path} has unsupported JSON value type {type(value).__name__}")
