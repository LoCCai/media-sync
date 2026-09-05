from __future__ import annotations

import ast
import base64
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from media_sync.integrations.mediacrawler import login_runner as runner
from media_sync.integrations.mediacrawler.checkout import VerifiedCheckout, verify_mediacrawler_checkout

_RASTER = b"synthetic-upstream-raster"
_ENCODED = base64.b64encode(_RASTER).decode("ascii")
_INLINE = "data:image/png;base64," + _ENCODED
_REMOTE = "https://synthetic.invalid/qr.png"
_PLATFORMS = ("xhs", "douyin", "kuaishou", "bilibili", "weibo", "tieba", "zhihu")


@pytest.fixture(scope="module")
def checkout() -> VerifiedCheckout:
    return verify_mediacrawler_checkout(
        Path(__file__).resolve().parents[2] / "upstreams.lock.json", license_acknowledged=True
    )


@pytest.mark.parametrize("platform", _PLATFORMS)
def test_each_pinned_login_passes_the_qr_helper_string_to_show_qrcode(
    checkout: VerifiedCheckout, platform: str
) -> None:
    source = checkout.root / "media_platform" / platform / "login.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    methods = [
        node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "login_by_qrcode"
    ]
    assert len(methods) == 1
    method = methods[0]
    helper_name = "find_qrcode_img_from_canvas" if platform == "zhihu" else "find_login_qrcode"
    assignments = [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Await)
        and isinstance(node.value.value, ast.Call)
        and ast.unparse(node.value.value.func) == f"utils.{helper_name}"
    ]
    assert assignments
    assert all(ast.unparse(node.targets[0]) == "base64_qrcode_img" for node in assignments)
    assert any(
        isinstance(node, ast.Call)
        and ast.unparse(node.func) == "functools.partial"
        and [ast.unparse(argument) for argument in node.args] == ["utils.show_qrcode", "base64_qrcode_img"]
        for node in ast.walk(method)
    )


@pytest.mark.parametrize("kind", ["inline", "remote", "canvas"])
async def test_actual_pinned_helpers_reach_the_relay_with_string_challenges(
    checkout: VerifiedCheckout, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """Run exact pinned helper AST, replacing only browser/network/viewer edges."""
    network_calls: list[str] = []
    observed_inputs: list[object] = []

    class Element:
        async def get_property(self, name: str) -> str:
            assert name == "src"
            return _REMOTE if kind == "remote" else _INLINE

        async def screenshot(self) -> bytes:
            assert kind == "canvas"
            return _RASTER

    class Page:
        async def wait_for_selector(self, selector: str) -> Element:
            assert selector == "synthetic-selector"
            return Element()

    class FakeNetworkClient:
        async def __aenter__(self) -> FakeNetworkClient:
            return self

        async def __aexit__(self, *_args: Any) -> None:
            pass

        async def get(self, url: str, *, headers: dict[str, str]) -> SimpleNamespace:
            assert url == _REMOTE
            assert headers == {"User-Agent": "synthetic-agent"}
            network_calls.append(url)
            return SimpleNamespace(status_code=200, content=_RASTER)

    def network_factory(*, follow_redirects: bool) -> FakeNetworkClient:
        assert follow_redirects is True
        return FakeNetworkClient()

    def forbidden_viewer(_value: object) -> None:
        pytest.fail("the upstream image viewer must never run")

    utils = SimpleNamespace(
        __file__=str(checkout.root / "tools" / "utils.py"),
        show_qrcode=forbidden_viewer,
        logger=SimpleNamespace(info=lambda *_args: None),
    )
    source = checkout.root / "tools" / "crawler_util.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    helpers = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name in {"find_login_qrcode", "find_qrcode_img_from_canvas"}
    ]
    assert len(helpers) == 2
    namespace: dict[str, Any] = {
        "base64": base64,
        "utils": utils,
        "make_async_client": network_factory,
        "get_user_agent": lambda: "synthetic-agent",
    }
    module = ast.fix_missing_locations(
        ast.Module(
            body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *helpers],
            type_ignores=[],
        )
    )
    exec(compile(module, str(source), "exec"), namespace)
    original_import = runner.importlib.import_module
    monkeypatch.setattr(
        runner.importlib,
        "import_module",
        lambda name: utils if name == "tools.utils" else original_import(name),
    )

    def normalize(value: object) -> bytes:
        observed_inputs.append(value)
        assert value == (_INLINE if kind == "inline" else _ENCODED)
        return _RASTER

    monkeypatch.setattr(runner, "_normalize_qr_image", normalize)
    destination = tmp_path / runner.LOGIN_QR_IMAGE_NAME
    with runner._disable_qr_export(checkout.root, destination):
        if kind == "canvas":
            result = await namespace["find_qrcode_img_from_canvas"](Page(), "synthetic-selector")
        else:
            result = await namespace["find_login_qrcode"](Page(), selector="synthetic-selector")
        assert isinstance(result, str)
        utils.show_qrcode(result)
    assert observed_inputs == [result]
    assert destination.read_bytes() == _RASTER
    assert utils.show_qrcode is forbidden_viewer
    assert network_calls == ([_REMOTE] if kind == "remote" else [])
