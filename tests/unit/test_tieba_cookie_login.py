"""Synthetic Tieba self evidence; no browser, credentials or platform request."""

from __future__ import annotations

import json
import time
from copy import deepcopy
from uuid import uuid4

import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler import cookie_login_runner as module
from media_sync.integrations.mediacrawler.cookie_login import (
    COOKIE_LOGIN_PLATFORMS,
    CookieLoginRequest,
    parse_cookie_header,
)

PORTRAIT = "tb.1.1234abcd." + "s" * 22
COOKIE = "BDUSS=PRIVATE_CANDIDATE==; STOKEN=OPTIONAL==; unrelated=kept"


def evidence() -> dict:
    return {"no": 0, "error": "", "data": {"id": 123456789, "portrait": PORTRAIT, "name": ""}}


def request(cookie: str = COOKIE) -> CookieLoginRequest:
    return CookieLoginRequest(uuid4(), Platform.TIEBA, uuid4(), parse_cookie_header(cookie))


@pytest.mark.parametrize("uid", [1, 123456789, 2**64 - 1])
@pytest.mark.parametrize("name", [None, "", "Changed nickname"])
def test_positive_immutable_self_id_and_portrait_not_mutable_nickname(uid: int, name: str | None) -> None:
    raw = evidence()
    raw["data"]["id"] = uid
    if name is None:
        raw["data"].pop("name")
    else:
        raw["data"]["name"] = name
    module._authenticated(Platform.TIEBA, raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("no", None),
        ("no", False),
        ("no", True),
        ("no", "0"),
        ("no", 0.0),
        ("no", -1),
        ("no", 1),
        ("no", 220021),
        ("data", None),
        ("data", []),
        ("data", {}),
        ("error", "PRIVATE_REMOTE_ERROR"),
        ("error", {"code": 401}),
        ("error", False),
    ],
)
def test_unknown_or_ambiguous_envelopes_are_invalid_not_claimed_auth_expiry(field: str, value: object) -> None:
    raw = evidence()
    if value is None:
        raw.pop(field)
    else:
        raw[field] = value
    with pytest.raises(module._VerificationFailure) as error:
        module._authenticated(Platform.TIEBA, raw)
    assert error.value.status == "result_invalid" and "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("uid", [None, False, True, 0, -1, 2**64, "123456789", 1.0, [], {}])
def test_public_profile_keys_guest_or_unbounded_ids_cannot_replace_self_id(uid: object) -> None:
    raw = evidence()
    raw["data"]["id"] = uid
    raw["data"]["user_id"] = 123456789
    raw["data"]["tieba_uid"] = 123456789
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        module._authenticated(Platform.TIEBA, raw)


@pytest.mark.parametrize(
    "portrait",
    [
        None,
        "",
        123,
        True,
        "x" * 36,
        "tb.1.short",
        "tb.1." + "x" * 32,
        "tb.1." + "x" * 27,
        "tb.1." + "x" * 27 + "/",
        "tb.1." + "x" * 27 + "?",
        "tb.1." + "x" * 27 + "中",
        PORTRAIT + "\n",
        " " + PORTRAIT,
        "tb.1.." + "x" * 29,
        PORTRAIT[:-1] + ".",
        "https://example.invalid/portrait",
        "tb.1." + "x" * 27 + "\\",
    ],
)
def test_only_bounded_modern_portrait_subset_is_accepted(portrait: object) -> None:
    raw = evidence()
    raw["data"]["portrait"] = portrait
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        module._authenticated(Platform.TIEBA, raw)


@pytest.mark.parametrize("level", ["root", "data"])
@pytest.mark.parametrize("value", [True, 1, "true", None])
def test_contradictory_guest_markers_do_not_authenticate(level: str, value: object) -> None:
    raw = evidence()
    target = raw if level == "root" else raw["data"]
    target["is_guest"] = value
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        module._authenticated(Platform.TIEBA, raw)


@pytest.mark.parametrize("length", [33, 34, 35, 36])
def test_documented_modern_portrait_lengths(length: int) -> None:
    raw = evidence()
    raw["data"]["portrait"] = "tb.1." + "x" * (length - 5)
    raw["data"]["guest"] = False
    module._authenticated(Platform.TIEBA, raw)


def test_tieba_frame_reports_only_bound_operation_status_not_private_identity() -> None:
    incoming = request()
    assert Platform.TIEBA in COOKIE_LOGIN_PLATFORMS
    result = module._result(incoming, "authenticated", "a" * 40)
    frame = module._result_frame(result)
    assert module._parse_result(frame[4:], incoming) == result
    decoded = json.loads(frame[4:])
    assert set(decoded) == {"schema_version", "status", "account_id", "platform", "operation_id", "upstream_sha"}
    assert all(value not in repr(result) + repr(incoming) + repr(decoded) for value in ("PRIVATE", PORTRAIT, "BDUSS"))


@pytest.mark.parametrize("cookie", ["LOGIN_STATUS=1", "STOKEN=present", "BDUSS=", 'BDUSS=""', "bduss=wrong-case"])
async def test_missing_bduss_candidate_never_loads_upstream_or_authenticates(cookie: str, tmp_path) -> None:
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        await module._verify_remote(tmp_path, request(cookie), time.monotonic() + 5)
    assert not list(tmp_path.iterdir())


def test_remote_parser_is_pure_and_does_not_rewrite_returned_identity() -> None:
    raw = evidence()
    original = deepcopy(raw)
    module._authenticated(Platform.TIEBA, raw)
    assert raw == original
