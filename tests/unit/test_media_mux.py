from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from media_sync.media import FFmpegStreamCopyMuxer, MediaDownloadError


class _Runner:
    def __init__(
        self,
        payload: bytes = b"muxed-mp4",
        error: BaseException | None = None,
        process_output: bytes = b"",
    ) -> None:
        self.payload = payload
        self.error = error
        self.process_output = process_output
        self.calls: list[tuple[tuple[str, ...], float, int]] = []

    def run(self, argv: Sequence[str], *, timeout_seconds: float, max_output_bytes: int) -> bytes:
        command = tuple(argv)
        self.calls.append((command, timeout_seconds, max_output_bytes))
        if self.error is not None:
            raise self.error
        Path(command[-1]).write_bytes(self.payload)
        return self.process_output


def _paths(tmp_path: Path, *, audio: bool = True) -> tuple[Path, Path | None, Path]:
    root = tmp_path / "work"
    root.mkdir()
    video = root / "video.part"
    video.write_bytes(b"video-component")
    audio_path = root / "audio.part" if audio else None
    if audio_path is not None:
        audio_path.write_bytes(b"audio-component")
    output = root / "final.part"
    output.write_bytes(b"")
    return video, audio_path, output


def test_ffmpeg_mux_uses_fixed_stream_copy_argv_and_bounds(tmp_path: Path) -> None:
    video, audio, output = _paths(tmp_path)
    assert audio is not None
    runner = _Runner()

    FFmpegStreamCopyMuxer("fixture-ffmpeg", runner=runner).mux(
        video,
        audio,
        output,
        root=tmp_path / "work",
        timeout_seconds=12.5,
        max_output_bytes=4096,
        max_media_bytes=8192,
    )

    assert output.read_bytes() == b"muxed-mp4"
    assert runner.calls == [
        (
            (
                "fixture-ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(video.absolute()),
                "-i",
                str(audio.absolute()),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c",
                "copy",
                "-strict",
                "unofficial",
                "-fs",
                "8192",
                "-f",
                "mp4",
                str(output.absolute()),
            ),
            12.5,
            4096,
        )
    ]


def test_ffmpeg_mux_accepts_silent_video_without_audio_mapping(tmp_path: Path) -> None:
    video, audio, output = _paths(tmp_path, audio=False)
    assert audio is None
    runner = _Runner()

    FFmpegStreamCopyMuxer(runner=runner).mux(
        video,
        None,
        output,
        root=tmp_path / "work",
        timeout_seconds=5,
        max_output_bytes=1024,
        max_media_bytes=2048,
    )

    argv = runner.calls[0][0]
    assert argv.count("-i") == 1
    assert "0:v:0" in argv
    assert "1:a:0" not in argv


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (FileNotFoundError(), "media_mux_unavailable"),
        (TimeoutError(), "media_mux_failed"),
        (RuntimeError(), "media_mux_failed"),
        (OverflowError(), "media_mux_failed"),
    ],
)
def test_ffmpeg_mux_translates_process_failures(
    tmp_path: Path,
    error: BaseException,
    expected: str,
) -> None:
    video, audio, output = _paths(tmp_path)

    with pytest.raises(MediaDownloadError) as caught:
        FFmpegStreamCopyMuxer(runner=_Runner(error=error)).mux(
            video,
            audio,
            output,
            root=tmp_path / "work",
            timeout_seconds=5,
            max_output_bytes=1024,
            max_media_bytes=2048,
        )

    assert caught.value.code == expected
    assert caught.value.retryable is True


@pytest.mark.parametrize("payload", [b"", b"x" * 17])
def test_ffmpeg_mux_rejects_empty_or_oversized_output(tmp_path: Path, payload: bytes) -> None:
    video, audio, output = _paths(tmp_path)

    with pytest.raises(MediaDownloadError) as caught:
        FFmpegStreamCopyMuxer(runner=_Runner(payload)).mux(
            video,
            audio,
            output,
            root=tmp_path / "work",
            timeout_seconds=5,
            max_output_bytes=1024,
            max_media_bytes=16,
        )

    assert caught.value.code == "media_mux_failed"


def test_ffmpeg_mux_defensively_rejects_runner_output_beyond_cap(tmp_path: Path) -> None:
    video, audio, output = _paths(tmp_path)

    with pytest.raises(MediaDownloadError) as caught:
        FFmpegStreamCopyMuxer(runner=_Runner(process_output=b"x" * 17)).mux(
            video,
            audio,
            output,
            root=tmp_path / "work",
            timeout_seconds=5,
            max_output_bytes=16,
            max_media_bytes=2048,
        )

    assert caught.value.code == "media_mux_failed"


def test_ffmpeg_mux_rejects_output_aliasing_an_input(tmp_path: Path) -> None:
    video, _audio, _output = _paths(tmp_path)
    runner = _Runner()

    with pytest.raises(MediaDownloadError) as caught:
        FFmpegStreamCopyMuxer(runner=runner).mux(
            video,
            None,
            video,
            root=tmp_path / "work",
            timeout_seconds=5,
            max_output_bytes=1024,
            max_media_bytes=2048,
        )

    assert caught.value.code == "filesystem_unsafe"
    assert runner.calls == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout_seconds": 0, "max_output_bytes": 1, "max_media_bytes": 1},
        {"timeout_seconds": 1, "max_output_bytes": 0, "max_media_bytes": 1},
        {"timeout_seconds": 1, "max_output_bytes": 1, "max_media_bytes": 0},
    ],
)
def test_ffmpeg_mux_rejects_nonpositive_limits(tmp_path: Path, kwargs: dict[str, float | int]) -> None:
    video, audio, output = _paths(tmp_path)

    with pytest.raises(ValueError, match="positive"):
        FFmpegStreamCopyMuxer(runner=_Runner()).mux(
            video,
            audio,
            output,
            root=tmp_path / "work",
            **kwargs,
        )


@pytest.mark.parametrize("executable", ["", "   ", " ffmpeg", "ffmpeg ", "ffmpeg\x00evil"])
def test_ffmpeg_mux_rejects_invalid_executable(executable: str) -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        FFmpegStreamCopyMuxer(executable)
