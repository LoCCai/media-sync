from __future__ import annotations

import base64
import io
import os
import warnings
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from media_sync.integrations.mediacrawler import login_runner as runner

_INPUT = b"synthetic-raster-input"
_ENCODED = base64.b64encode(_INPUT).decode("ascii")
_OUTPUT = b"synthetic-normalized-png"


class FakeImage:
    format = "PNG"
    size = (32, 32)
    n_frames = 1

    def __init__(self) -> None:
        self.loaded = False
        self.info = {"private-metadata": "MUST-NOT-ESCAPE"}
        self.output = _OUTPUT

    def __enter__(self) -> FakeImage:
        return self

    def __exit__(self, *_args: Any) -> None:
        pass

    def load(self) -> None:
        self.loaded = True

    def convert(self, mode: str) -> FakeImage:
        assert self.loaded
        assert mode == "RGBA"
        return self

    def save(self, output: Any, *, format: str) -> None:
        assert format == "PNG"
        assert self.info == {}
        output.write(self.output)


@pytest.fixture
def decoder(monkeypatch: pytest.MonkeyPatch) -> FakeImage:
    raster = FakeImage()

    def open_image(stream: io.BytesIO, *, formats: tuple[str, ...]) -> FakeImage:
        assert stream.getvalue() == _INPUT
        assert formats == ("PNG", "JPEG", "WEBP")
        return raster

    original = runner.importlib.import_module

    def import_module(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "PIL.Image":
            return SimpleNamespace(open=open_image)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(runner.importlib, "import_module", import_module)
    return raster


@pytest.mark.parametrize("value", [b"legacy-bytes", bytearray(b"legacy-bytes")])
def test_legacy_bytes_are_exact_and_do_not_import_pillow(value: object, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner.importlib, "import_module", lambda *_args: pytest.fail("unexpected decoder import"))
    assert runner._normalize_qr_image(value) == b"legacy-bytes"


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        1,
        [],
        {},
        memoryview(b"unsupported"),
        b"",
        bytearray(),
        "",
        "https://synthetic.invalid/QR-SECRET",
        "C:/synthetic/QR-SECRET.png",
        "file:///synthetic/QR-SECRET.png",
        "data:image/svg+xml;base64,PHN2Zy8+",
        "data:text/plain;base64,UVItU0VDUkVU",
        "data:image/gif;base64,UVItU0VDUkVU",
        "data:image/png;charset=utf-8;base64," + _ENCODED,
        "data:image/png," + _ENCODED,
        "data:image/png;base64,",
        " " + _ENCODED,
        _ENCODED + "\n",
        _ENCODED.rstrip("="),
        _ENCODED + "=",
        "====",
        "a===",
        "Zh==",  # Non-canonical padding bits; the canonical encoding is Zg==.
        "二维码",
    ],
)
def test_unsupported_and_malformed_values_never_reach_decoder(value: object, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner.importlib, "import_module", lambda *_args: pytest.fail("unexpected decoder import"))
    assert runner._normalize_qr_image(value) is None


def test_size_bounds_are_checked_before_decoder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner.importlib, "import_module", lambda *_args: pytest.fail("unexpected decoder import"))
    assert runner._normalize_qr_image(b"x" * (runner._MAX_QR_IMAGE_BYTES + 1)) is None
    assert runner._normalize_qr_image("A" * (runner._MAX_QR_ENCODED_CHARACTERS + 1)) is None
    # Exercise the independent decoded limit without allocating large images.
    monkeypatch.setattr(runner, "_MAX_QR_IMAGE_BYTES", len(_INPUT) - 1)
    assert runner._normalize_qr_image(_ENCODED) is None


@pytest.mark.parametrize(
    ("prefix", "image_format"),
    [
        ("", "PNG"),
        ("data:image/png;base64,", "PNG"),
        ("data:image/jpeg;base64,", "JPEG"),
        ("data:image/webp;base64,", "WEBP"),
    ],
)
def test_supported_strings_are_normalized_to_png(decoder: FakeImage, prefix: str, image_format: str) -> None:
    decoder.format = image_format
    assert runner._normalize_qr_image(prefix + _ENCODED) == _OUTPUT
    assert decoder.loaded


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("size", (0, 2)),
        ("size", (2, 0)),
        ("size", (4097, 1)),
        ("size", (1, 4097)),
        ("size", (4096, 4096)),
        ("n_frames", 2),
        ("format", "GIF"),
        ("format", "SVG"),
    ],
)
def test_dimensions_frames_and_formats_are_rejected_before_load(decoder: FakeImage, attribute: str, value: Any) -> None:
    setattr(decoder, attribute, value)
    assert runner._normalize_qr_image(_ENCODED) is None
    assert not decoder.loaded


def test_data_uri_format_must_match_the_image(decoder: FakeImage) -> None:
    assert runner._normalize_qr_image("data:image/jpeg;base64," + _ENCODED) is None
    assert not decoder.loaded


def test_output_limit_is_enforced_while_encoding(decoder: FakeImage, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "_MAX_QR_IMAGE_BYTES", len(_INPUT))
    decoder.output = b"x" * (len(_INPUT) + 1)
    assert runner._normalize_qr_image(_ENCODED) is None
    with runner._BoundedQrBuffer() as output:
        output.write(b"x" * len(_INPUT))
        with pytest.raises(ValueError, match=r"^QR image exceeds the relay size limit$"):
            output.write(b"x")
        assert len(output.getvalue()) == len(_INPUT)


@pytest.mark.parametrize("error", [ImportError("QR-SECRET"), ValueError("QR-SECRET"), OSError("QR-SECRET")])
def test_decoder_failures_are_non_fatal_and_silent(
    error: Exception, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> Any:
        raise error

    monkeypatch.setattr(runner.importlib, "import_module", fail)
    assert runner._normalize_qr_image(_ENCODED) is None
    assert capsys.readouterr() == ("", "")


def test_decoder_warnings_do_not_escape(
    decoder: FakeImage, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def warn() -> None:
        warnings.warn("QR-SECRET", UserWarning, stacklevel=1)

    monkeypatch.setattr(decoder, "load", warn)
    assert runner._normalize_qr_image(_ENCODED) is None
    assert capsys.readouterr() == ("", "")


@pytest.fixture
def upstream_utils(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    def forbidden_viewer(_value: object) -> None:
        pytest.fail("the upstream image viewer must never be called")

    utils = SimpleNamespace(__file__=str(tmp_path / "tools" / "utils.py"), show_qrcode=forbidden_viewer)
    original = runner.importlib.import_module

    def import_module(name: str, *args: Any, **kwargs: Any) -> Any:
        return utils if name == "tools.utils" else original(name, *args, **kwargs)

    monkeypatch.setattr(runner.importlib, "import_module", import_module)
    return utils


def test_relay_is_atomic_confined_restored_and_silent(
    tmp_path: Path, upstream_utils: SimpleNamespace, decoder: FakeImage, capsys: pytest.CaptureFixture[str]
) -> None:
    original = upstream_utils.show_qrcode
    destination = tmp_path / runner.LOGIN_QR_IMAGE_NAME
    with runner._disable_qr_export(tmp_path, destination):
        upstream_utils.show_qrcode("data:image/png;base64," + _ENCODED)
        assert destination.read_bytes() == _OUTPUT
        upstream_utils.show_qrcode(b"legacy-bytes")
        assert destination.read_bytes() == b"legacy-bytes"
        upstream_utils.show_qrcode("invalid-QR-SECRET")
        assert destination.read_bytes() == b"legacy-bytes"
    assert upstream_utils.show_qrcode is original
    assert sorted(path.name for path in tmp_path.iterdir()) == [runner.LOGIN_QR_IMAGE_NAME]
    if os.name != "nt":
        assert destination.stat().st_mode & 0o777 == 0o600
    assert capsys.readouterr() == ("", "")


def test_relay_write_failure_cleans_temporary_and_preserves_previous_image(
    tmp_path: Path, upstream_utils: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / runner.LOGIN_QR_IMAGE_NAME
    destination.write_bytes(b"previous")

    def fail_replace(*_args: Any) -> None:
        raise OSError("QR-SECRET")

    monkeypatch.setattr(runner.os, "replace", fail_replace)
    with runner._disable_qr_export(tmp_path, destination):
        upstream_utils.show_qrcode(b"new")
    assert destination.read_bytes() == b"previous"
    assert sorted(path.name for path in tmp_path.iterdir()) == [runner.LOGIN_QR_IMAGE_NAME]


def test_no_destination_is_a_noop_and_restores_original_after_exception(
    tmp_path: Path, upstream_utils: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = upstream_utils.show_qrcode
    monkeypatch.setattr(runner, "_normalize_qr_image", lambda *_args: pytest.fail("unexpected normalization"))
    with pytest.raises(RuntimeError, match="synthetic"), runner._disable_qr_export(tmp_path):
        upstream_utils.show_qrcode(_ENCODED)
        raise RuntimeError("synthetic")
    assert upstream_utils.show_qrcode is original
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("image_format", ["PNG", "JPEG", "WEBP"])
@pytest.mark.parametrize("data_uri", [False, True])
def test_real_upstream_pillow_rasters_become_valid_png(image_format: str, data_uri: bool) -> None:
    image_module = pytest.importorskip("PIL.Image", reason="requires the isolated upstream Pillow dependency")
    with image_module.new("RGB", (32, 32), (12, 23, 34)) as source, io.BytesIO() as original:
        source.save(original, format=image_format)
        encoded = base64.b64encode(original.getvalue()).decode("ascii")
    if data_uri:
        encoded = f"data:image/{image_format.lower()};base64," + encoded
    result = runner._normalize_qr_image(encoded)
    assert result is not None and result.startswith(b"\x89PNG\r\n\x1a\n")
    with image_module.open(io.BytesIO(result)) as restored:
        restored.load()
        assert restored.format == "PNG"
        assert restored.size == (32, 32)
        assert restored.mode == "RGBA"


def test_real_pillow_rejects_corrupt_animated_and_oversized_rasters() -> None:
    image_module = pytest.importorskip("PIL.Image", reason="requires the isolated upstream Pillow dependency")
    assert runner._normalize_qr_image(base64.b64encode(b"not-a-raster").decode("ascii")) is None
    for dimensions, animated in [((4097, 1), False), ((32, 32), True)]:
        with (
            image_module.new("RGB", dimensions) as first,
            image_module.new("RGB", dimensions, "white") as second,
            io.BytesIO() as encoded,
        ):
            first.save(encoded, format="PNG", save_all=animated, append_images=[second] if animated else [])
            assert runner._normalize_qr_image(base64.b64encode(encoded.getvalue()).decode("ascii")) is None
