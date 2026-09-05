"""Synthetic exact HTML/transport tests; no platform/CDN connection."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import pytest

from media_sync.integrations.mediacrawler import zhihu_creator_profile as module
from media_sync.integrations.mediacrawler.creator_profile_runner import _LookupFailure

TOKEN = "synthetic-creator.name_01"
COOKIE = 'z_c0=PRIVATE_TEST_COOKIE==; d_c0=PRIVATE_SIGN==; marker="quoted=="'


def _html(row: object | None = None) -> str:
    return (
        '<html><script id="js-initialData">'
        + json.dumps(
            {
                "initialState": {
                    "entities": {
                        "users": {
                            TOKEN: row
                            if row is not None
                            else {
                                "urlToken": TOKEN,
                                "name": "原始平台昵称",
                                "avatarUrl": "https://unknown.example/private-avatar",
                                "private": "not-retained",
                            }
                        }
                    }
                }
            },
            ensure_ascii=False,
        )
        + "</script></html>"
    )


def _headers() -> dict[str, str]:
    return {
        "User-Agent": "offline-desktop",
        "cookie": COOKIE,
        "Origin": "https://www.zhihu.com",
        "Referer": "https://www.zhihu.com/",
        "Content-Type": "application/json;charset=UTF-8",
        "x-api-version": "3.0.91",
        "x-app-za": "OS=Web",
        "x-requested-with": "fetch",
        "x-zse-93": "101_3_3.0",
        "x-zst-81": "signed-81",
        "x-zse-96": "signed-96",
    }


def test_exact_response_token_and_raw_name_only() -> None:
    result = module.parse_zhihu_profile_html(_html(), TOKEN)
    assert result.remote_id == TOKEN and result.display_name == "原始平台昵称" and result.avatar_url is None
    assert "unknown.example" not in repr(result) and "not-retained" not in repr(result)


@pytest.mark.parametrize("escaped", [r"\ud800", r"\udfff", r"valid\ud800name"])
def test_escaped_lone_surrogate_is_rejected_before_result_frame(escaped: str) -> None:
    # Input HTML itself is valid UTF-8; the invalid scalar appears only after
    # decoding the JSON escape, so the outer HTML byte check is insufficient.
    html = _html({"urlToken": TOKEN, "name": "replace-me"}).replace("replace-me", escaped)
    html.encode("utf-8")
    with pytest.raises(_LookupFailure, match="result_invalid"):
        module.parse_zhihu_profile_html(html, TOKEN)


def test_valid_escaped_unicode_pair_remains_a_displayable_nickname() -> None:
    html = _html({"urlToken": TOKEN, "name": "replace-me"}).replace("replace-me", r"\ud83d\ude00")
    assert module.parse_zhihu_profile_html(html, TOKEN).display_name == "😀"


@pytest.mark.parametrize(
    "row",
    [
        {},
        {"name": "name"},
        {"urlToken": "different", "name": "name"},
        {"urlToken": 123, "name": "name"},
        {"urlToken": TOKEN, "name": None},
        {"urlToken": TOKEN, "name": "\nsecret"},
        {"urlToken": TOKEN, "name": "x" * 513},
        {"urlToken": TOKEN, "name": " "},
        ["not-a-row"],
    ],
)
def test_missing_mismatched_response_identity_never_falls_back_to_input(row: Any) -> None:
    with pytest.raises(_LookupFailure, match="result_invalid"):
        module.parse_zhihu_profile_html(_html(row), TOKEN)


@pytest.mark.parametrize(
    "change",
    [
        "missing_script",
        "wrong_script",
        "duplicate_script",
        "duplicate_id_attr",
        "unclosed",
        "selfclosed",
        "duplicate_json",
        "nan",
        "array",
        "wrong_key",
        "oversize",
        "malformed",
    ],
)
def test_strict_unique_initial_data_and_size(change: str) -> None:
    html = _html()
    if change == "missing_script":
        html = "<html>Login required</html>"
    elif change == "wrong_script":
        html = html.replace("js-initialData", "other")
    elif change == "duplicate_script":
        html += html
    elif change == "duplicate_id_attr":
        html = html.replace('id="js-initialData"', 'id="js-initialData" id="other"')
    elif change == "unclosed":
        html = html.replace("</script>", "")
    elif change == "selfclosed":
        html = '<script id="js-initialData"/>'
    elif change == "duplicate_json":
        html = html.replace('"urlToken":', '"name": "other", "urlToken":')
    elif change == "nan":
        html = html.replace('"private": "not-retained"', '"private": NaN')
    elif change == "array":
        html = '<script id="js-initialData">[]</script>'
    elif change == "wrong_key":
        html = html.replace('"' + TOKEN + '":', '"other":')
    elif change == "oversize":
        html += "x" * module.MAX_PROFILE_HTML_BYTES
    else:
        html = '<script id="js-initialData">malformed</script>'
    with pytest.raises(_LookupFailure, match="result_invalid"):
        module.parse_zhihu_profile_html(html, TOKEN)


@pytest.mark.parametrize("token", [".", "..", "", "/", "a/b", "%61", "a?b", "a#b", "a\\b", "中文", "a" * 256, " a"])
def test_noncanonical_tokens_rejected(token: str) -> None:
    with pytest.raises(_LookupFailure):
        module.parse_zhihu_profile_html(_html(), token)


@pytest.mark.parametrize("html", [False, True])
@pytest.mark.parametrize(
    "change",
    [
        None,
        "redirect",
        "status",
        "encoding",
        "content_type",
        "length",
        "stream_size",
        "private_dns",
        "cookie_drop",
        "sign_drop",
        "duplicate_header",
        "bad_url",
        "expired_deadline",
    ],
)
def test_bounded_pinned_http_never_follows_or_forwards_unapproved_inputs(
    monkeypatch: pytest.MonkeyPatch, html: bool, change: str | None
) -> None:
    import media_sync.media.network as network

    requests: list[httpx.Request] = []
    maximum = module.MAX_PROFILE_HTML_BYTES if html else module.MAX_PROFILE_API_BYTES
    payload = _html().encode() if html else b'{"uid":"123","name":"self"}'
    headers = _headers()
    url = "https://www.zhihu.com" + ("/people/" + TOKEN if html else "/api/v4/me")
    if change == "cookie_drop":
        del headers["cookie"]
    elif change == "sign_drop":
        del headers["x-zse-96"]
    elif change == "duplicate_header":
        headers["Cookie"] = COOKIE
    elif change == "bad_url":
        url += "?include=email"

    def transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["cookie"] == COOKIE
        assert request.headers["x-zst-81"] == "signed-81" and request.headers["x-zse-96"] == "signed-96"
        assert request.headers["accept-encoding"] == "identity" and request.url.query == b""
        if change == "redirect":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        response_headers = {"content-type": "text/html" if html else "application/json"}
        if change == "encoding":
            response_headers["content-encoding"] = "gzip"
        elif change == "content_type":
            response_headers["content-type"] = "application/octet-stream"
        elif change == "length":
            response_headers["content-length"] = str(maximum + 1)
        data = b"x" * (maximum + 1) if change == "stream_size" else payload
        return httpx.Response(
            403 if change == "status" else 200, headers=response_headers, stream=httpx.ByteStream(data)
        )

    monkeypatch.setattr(
        network.SocketAddressResolver, "resolve", lambda *args: ["127.0.0.1" if change == "private_dns" else "8.8.8.8"]
    )
    monkeypatch.setattr(network, "PinnedHTTPTransport", lambda target: httpx.MockTransport(transport))
    if change is None:
        assert module._fetch(url, headers, time.monotonic() + 5, token=TOKEN, html=html) == payload
    else:
        with pytest.raises(_LookupFailure):
            module._fetch(
                url, headers, time.monotonic() + (-1 if change == "expired_deadline" else 5), token=TOKEN, html=html
            )
    assert len(requests) == int(
        change not in {"private_dns", "cookie_drop", "sign_drop", "duplicate_header", "bad_url", "expired_deadline"}
    )
