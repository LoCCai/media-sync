"""Bounded fixed-argument ffmpeg stream-copy muxing."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from media_sync.media.errors import MediaDownloadError
from media_sync.media.probe import SubprocessProbeRunner
from media_sync.security.paths import PathSecurityError, assert_regular_file


class MuxProcessRunner(Protocol):
    """Injectable bounded child-process runner."""

    def run(self, argv: Sequence[str], *, timeout_seconds: float, max_output_bytes: int) -> bytes: ...


class MediaMuxer(Protocol):
    """Merge one video component and optional audio without transcoding."""

    def mux(
        self,
        video_path: Path,
        audio_path: Path | None,
        output_path: Path,
        *,
        root: Path,
        timeout_seconds: float,
        max_output_bytes: int,
        max_media_bytes: int,
    ) -> None: ...


class FFmpegStreamCopyMuxer:
    """Run ffmpeg with a closed MP4 stream-copy command and bounded output."""

    def __init__(self, executable: str = "ffmpeg", *, runner: MuxProcessRunner | None = None) -> None:
        if (
            not isinstance(executable, str)
            or not executable
            or executable != executable.strip()
            or "\x00" in executable
        ):
            raise ValueError("ffmpeg executable must not be blank")
        self._executable = executable
        self._runner = runner or SubprocessProbeRunner()

    def mux(
        self,
        video_path: Path,
        audio_path: Path | None,
        output_path: Path,
        *,
        root: Path,
        timeout_seconds: float,
        max_output_bytes: int,
        max_media_bytes: int,
    ) -> None:
        if timeout_seconds <= 0 or max_output_bytes <= 0 or max_media_bytes <= 0:
            raise ValueError("mux limits must be positive")
        try:
            video = assert_regular_file(video_path, root=root)
            audio = None if audio_path is None else assert_regular_file(audio_path, root=root)
            before = assert_regular_file(output_path, root=root)
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc
        if video.st_size <= 0 or (audio is not None and audio.st_size <= 0):
            raise MediaDownloadError("media_mux_failed")
        identities = [(video.st_dev, video.st_ino), (before.st_dev, before.st_ino)]
        if audio is not None:
            identities.append((audio.st_dev, audio.st_ino))
        if len(set(identities)) != len(identities):
            raise MediaDownloadError("filesystem_unsafe")

        argv = [
            self._executable,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path.absolute()),
        ]
        if audio_path is not None:
            argv.extend(("-i", str(audio_path.absolute())))
        argv.extend(("-map", "0:v:0"))
        if audio_path is not None:
            argv.extend(("-map", "1:a:0"))
        argv.extend(
            (
                "-c",
                "copy",
                "-strict",
                "unofficial",
                "-fs",
                str(max_media_bytes),
                "-f",
                "mp4",
                str(output_path.absolute()),
            )
        )
        try:
            output = self._runner.run(tuple(argv), timeout_seconds=timeout_seconds, max_output_bytes=max_output_bytes)
            if len(output) > max_output_bytes:
                raise MediaDownloadError("media_mux_failed")
        except FileNotFoundError as exc:
            raise MediaDownloadError("media_mux_unavailable") from exc
        except (OSError, RuntimeError, TimeoutError, OverflowError, ValueError) as exc:
            raise MediaDownloadError("media_mux_failed") from exc

        try:
            after = assert_regular_file(output_path, root=root)
        except PathSecurityError as exc:
            raise MediaDownloadError("filesystem_unsafe") from exc
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise MediaDownloadError("filesystem_unsafe")
        if after.st_size <= 0 or after.st_size > max_media_bytes:
            raise MediaDownloadError("media_mux_failed")
        if os.name != "nt" and after.st_nlink != 1:
            raise MediaDownloadError("filesystem_unsafe")


__all__ = ["FFmpegStreamCopyMuxer", "MediaMuxer", "MuxProcessRunner"]
