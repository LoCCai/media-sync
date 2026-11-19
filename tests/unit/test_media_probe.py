from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from media_sync.media import FFprobeMediaProbe, ProbeResult, SubprocessProbeRunner


class _Runner:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls: list[tuple[tuple[str, ...], float, int]] = []

    def run(self, argv: Sequence[str], *, timeout_seconds: float, max_output_bytes: int) -> bytes:
        self.calls.append((tuple(argv), timeout_seconds, max_output_bytes))
        return self.payload


def test_ffprobe_uses_fixed_argv_and_allowlisted_mapping(tmp_path: Path) -> None:
    runner = _Runner(
        b'{"format":{"format_name":"mov,mp4,m4a,3gp,3g2,mj2"},"streams":[{"codec_type":"audio","codec_name":"aac"}]}'
    )
    probe = FFprobeMediaProbe("fake-ffprobe", runner=runner)
    media = tmp_path / "asset with spaces.part"

    result = probe.probe(media, timeout_seconds=2.0, max_output_bytes=4096)

    assert result == ProbeResult("audio/mp4", "m4a")
    argv, timeout, output_limit = runner.calls[0]
    assert argv[:7] == (
        "fake-ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=format_name:stream=codec_type,codec_name",
        "-of",
        "json",
    )
    assert argv[-1] == str(media.absolute())
    assert timeout == 2.0
    assert output_limit == 4096


def test_ffprobe_rejects_runner_output_beyond_declared_cap(tmp_path: Path) -> None:
    probe = FFprobeMediaProbe("fake-ffprobe", runner=_Runner(b"x" * 101))
    with pytest.raises(OverflowError):
        probe.probe(tmp_path / "media", timeout_seconds=1.0, max_output_bytes=100)


def test_ffprobe_accepts_only_video_bearing_flv(tmp_path: Path) -> None:
    video = FFprobeMediaProbe(
        "fake-ffprobe",
        runner=_Runner(b'{"format":{"format_name":"flv"},"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}'),
    )
    audio_only = FFprobeMediaProbe(
        "fake-ffprobe",
        runner=_Runner(b'{"format":{"format_name":"flv"},"streams":[{"codec_type":"audio"}]}'),
    )

    assert video.probe(tmp_path / "mixed.flv", timeout_seconds=1.0, max_output_bytes=4096) == ProbeResult(
        "video/x-flv", "flv"
    )
    assert audio_only.probe(tmp_path / "audio.flv", timeout_seconds=1.0, max_output_bytes=4096) is None


def test_subprocess_probe_runner_enforces_timeout_and_combined_output_cap() -> None:
    runner = SubprocessProbeRunner()
    with pytest.raises(TimeoutError):
        runner.run(
            (sys.executable, "-c", "import time; time.sleep(2)"),
            timeout_seconds=0.1,
            max_output_bytes=1024,
        )
    with pytest.raises(OverflowError):
        runner.run(
            (sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x' * 10000)"),
            timeout_seconds=2.0,
            max_output_bytes=128,
        )


def test_media_child_environment_withholds_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """ffprobe/ffmpeg children must not inherit an `env:`-resolved secret."""

    from media_sync.media.probe import media_child_environment

    monkeypatch.setenv("MEDIA_SYNC_OPERATOR_CREDENTIAL_SECRET", "SENTINEL-operator-secret")
    monkeypatch.setenv("MEDIA_SYNC_MEDIA_SERVER_API_KEY", "SENTINEL-media-server-key")
    monkeypatch.setenv("SOME_PLATFORM_COOKIE", "SENTINEL-cookie")
    monkeypatch.setenv("PATH", "/usr/bin")

    environment = media_child_environment()

    assert environment["PATH"] == "/usr/bin"
    assert not any("SENTINEL" in value for value in environment.values())
    assert set(environment) <= {
        "COMSPEC",
        "HOME",
        "LANG",
        "LC_ALL",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMW6432",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USERPROFILE",
        "WINDIR",
    }
