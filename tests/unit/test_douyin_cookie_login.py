"""Douyin remote-self authentication's strict, secret-free success subset."""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest

from media_sync.integrations.mediacrawler import douyin_cookie_login as module
from media_sync.security.secrets import SecretValue

COOKIE = 'sessionid=PRIVATE_NEW==; marker="quoted=="; uid_tt=PRIVATE_CANDIDATE'


def response() -> dict[str, Any]:
    return {
        "status_code": 0,
        "user": {"uid": "123456789", "sec_uid": "MS4wLjABAAAA-PRIVATE_SELF", "nickname": "本人昵称"},
    }


@pytest.mark.parametrize("uid", [1, 2**64 - 1, "1", str(2**64 - 1)])
def test_explicit_uid_types_and_exact_returned_identity_only(uid):
    raw = response()
    raw["user"]["uid"] = uid
    assert module._authenticated(raw) is None


@pytest.mark.parametrize(
    "uid", [None, True, False, 0, -1, 1.0, 2**64, "", "0", "01", "+1", " 1", "\uff11", "1e2", "x" * 100]
)
def test_uid_is_not_coerced_or_guessed(uid):
    raw = response()
    raw["user"]["uid"] = uid
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        module._authenticated(raw)


@pytest.mark.parametrize("value", [None, True, 1, "", "a" * 256, "a.b", "a/b", "a\n", "中文", "a%2fb"])
def test_sec_uid_must_be_safe_exact_response_string(value):
    raw = response()
    raw["user"]["sec_uid"] = value
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        module._authenticated(raw)


@pytest.mark.parametrize("value", [None, True, 1, "", "   ", "x" * 513, "bad\nprivate", "bad\x7fname", "bad\ud800"])
def test_raw_self_nickname_is_not_coerced_or_filled(value):
    raw = response()
    raw["user"]["nickname"] = value
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        module._authenticated(raw)


@pytest.mark.parametrize("value", [None, False, True, 0.0, "0", 401, 403, -1])
def test_unknown_or_noninteger_status_never_classifies_expired(value):
    raw = response()
    raw["status_code"] = value
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        module._authenticated(raw)


@pytest.mark.parametrize("wrapper", ["root", "user"])
@pytest.mark.parametrize("key", ["guest", "isGuest", "is_guest"])
@pytest.mark.parametrize("value", [True, 0, None, "false"])
def test_guest_flags_are_exact_false_or_absent(wrapper, key, value):
    raw = response()
    row = raw if wrapper == "root" else raw["user"]
    row[key] = value
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        module._authenticated(raw)
    row[key] = False
    assert module._authenticated(raw) is None


@pytest.mark.parametrize("wrapper", ["root", "user"])
@pytest.mark.parametrize("key", ["isLogin", "is_login", "loggedIn"])
@pytest.mark.parametrize("value", [False, 0, None, "true"])
def test_present_login_flags_cannot_contradict_success_identity(wrapper, key, value):
    raw = response()
    row = raw if wrapper == "root" else raw["user"]
    row[key] = value
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        module._authenticated(raw)
    row[key] = True
    assert module._authenticated(raw) is None


@pytest.mark.parametrize("value", [None, [], "private", True, {}])
def test_missing_or_wrong_user_wrapper_cannot_be_public_profile_or_local_flag(value):
    raw = response()
    raw.update({"user": value, "LOGIN_STATUS": "1", "HasUserLogin": "1", "uid_tt": "LOCAL"})
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        module._authenticated(raw)


@pytest.mark.parametrize("value", [{"uid": "123456789"}, {"uid": "999"}, "private", [], False])
def test_alternative_nonempty_or_malformed_wrapper_is_not_a_fallback(value):
    raw = response()
    raw["user_info"] = value
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        module._authenticated(raw)


@pytest.mark.parametrize("key,value", [("error", "PRIVATE"), ("error", {}), ("errors", ["PRIVATE"]), ("errors", {})])
def test_conflicting_error_payload_cannot_authenticate(key, value):
    raw = response()
    raw[key] = value
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        module._authenticated(raw)


async def test_candidate_is_passed_once_and_no_identity_is_returned(monkeypatch, capsys):
    seen = []

    def fetch(cookie, deadline):
        seen.append(cookie)
        return response()

    monkeypatch.setattr(module, "_fetch_self", fetch)
    assert await module.verify_douyin_cookie(SecretValue(COOKIE), time.monotonic() + 5) is None
    assert seen == [COOKIE]
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize(
    "failure,status",
    [
        (RuntimeError("PRIVATE_COOKIE_IN_HTTP_ERROR"), "result_invalid"),
        (ValueError("PRIVATE_BODY"), "result_invalid"),
        (httpx.ConnectError("PRIVATE_NETWORK_DIAGNOSTIC"), "verification_unavailable"),
        (httpx.ReadTimeout("PRIVATE_TIMEOUT"), "timed_out"),
        (TimeoutError("PRIVATE_TIMEOUT"), "timed_out"),
    ],
)
async def test_private_exception_text_is_never_public(monkeypatch, failure, status):
    def fetch(*args):
        raise failure

    monkeypatch.setattr(module, "_fetch_self", fetch)
    with pytest.raises(module._VerificationFailure, match="^" + status + "$") as caught:
        await module.verify_douyin_cookie(SecretValue(COOKIE), time.monotonic() + 5)
    assert "PRIVATE" not in str(caught.value) and caught.value.__suppress_context__ is True


@pytest.mark.parametrize("deadline", [True, None, float("nan"), float("inf"), "1"])
async def test_invalid_budget_never_reaches_transport(monkeypatch, deadline):
    monkeypatch.setattr(module, "_fetch_self", lambda *args: pytest.fail("invalid deadline reached HTTP"))
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        await module.verify_douyin_cookie(SecretValue(COOKIE), deadline)


async def test_expired_deadline_never_reaches_transport(monkeypatch):
    monkeypatch.setattr(module, "_fetch_self", lambda *args: pytest.fail("late HTTP"))
    with pytest.raises(module._VerificationFailure, match=r"^timed_out$"):
        await module.verify_douyin_cookie(SecretValue(COOKIE), time.monotonic() - 1)


async def test_plain_cookie_string_is_not_accepted_by_typed_boundary(monkeypatch):
    monkeypatch.setattr(module, "_fetch_self", lambda *args: pytest.fail("plain secret reached HTTP"))
    with pytest.raises(module._VerificationFailure, match=r"^result_invalid$"):
        await module.verify_douyin_cookie(COOKIE, time.monotonic() + 5)


async def test_late_success_cannot_authenticate(monkeypatch):
    deadline = time.monotonic() + 5

    def fetch(*args):
        monkeypatch.setattr(module.time, "monotonic", lambda: deadline + 1)
        return response()

    monkeypatch.setattr(module, "_fetch_self", fetch)
    with pytest.raises(module._VerificationFailure, match=r"^timed_out$"):
        await module.verify_douyin_cookie(SecretValue(COOKIE), deadline)
