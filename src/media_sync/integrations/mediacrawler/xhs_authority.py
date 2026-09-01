"""Closed validation helpers for ephemeral Xiaohongshu authority URLs."""

from __future__ import annotations

from urllib.parse import SplitResult, parse_qsl, urlsplit

_XHS_HOSTS = frozenset({"xiaohongshu.com", "www.xiaohongshu.com"})


def validate_xhs_detail_reference(value: str, content_remote_id: str) -> str:
    """Return one exact note authority URL or raise ``ValueError``."""

    _bounded_text(value, maximum=4_096)
    _bounded_text(content_remote_id, maximum=512)
    parsed, query = _split_authority_url(value)
    path_parts = parsed.path.rstrip("/").split("/")
    allowed_path = (
        len(path_parts) == 3
        and path_parts[0] == ""
        and path_parts[1] in {"explore", "discovery"}
        and path_parts[2] == content_remote_id
    ) or (len(path_parts) == 4 and path_parts[:3] == ["", "discovery", "item"] and path_parts[3] == content_remote_id)
    if not allowed_path:
        raise ValueError("invalid XHS note authority")
    _validate_xsec_query(query)
    return value


def validate_xhs_creator_reference(value: str, author_remote_id: str) -> str:
    """Return one exact creator authority URL or raise ``ValueError``."""

    _bounded_text(value, maximum=4_096)
    _bounded_text(author_remote_id, maximum=255)
    parsed, query = _split_authority_url(value)
    if parsed.path != f"/user/profile/{author_remote_id}":
        raise ValueError("invalid XHS creator authority")
    _validate_xsec_query(query)
    return value


def _split_authority_url(value: str) -> tuple[SplitResult, list[tuple[str, str]]]:
    try:
        parsed = urlsplit(value)
        port = parsed.port
        query = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=64,
        )
    except ValueError as exc:
        raise ValueError("invalid XHS authority URL") from exc
    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname not in _XHS_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.fragment
    ):
        raise ValueError("invalid XHS authority URL")
    return parsed, query


def _validate_xsec_query(query: list[tuple[str, str]]) -> None:
    values: dict[str, list[str]] = {}
    for key, value in query:
        values.setdefault(key, []).append(value)
    for required in ("xsec_token", "xsec_source"):
        candidates = values.get(required, [])
        if len(candidates) != 1 or not candidates[0]:
            raise ValueError("invalid XHS authority query")


def _bounded_text(value: object, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid XHS authority text")
    if not value or value.strip() != value or len(value) > maximum:
        raise ValueError("invalid XHS authority text")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValueError("invalid XHS authority text")
    return value


__all__ = ["validate_xhs_creator_reference", "validate_xhs_detail_reference"]
