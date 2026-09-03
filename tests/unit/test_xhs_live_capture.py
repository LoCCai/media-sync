"""Execution 0039 capture matrix for the XHS live-photo list shim."""

from __future__ import annotations

from typing import Any

from media_sync.integrations.mediacrawler.xhs_live import (
    XHS_LIVE_MAX_PAIRS,
    XHS_LIVE_VIDEO_FIELD,
    XHS_LIVE_VIDEO_LIST_FIELD,
    capture_xhs_live_fields,
)


def _image(url: str | None = "http://sns-video-bd.xhscdn.com/live-stream.mp4") -> dict[str, Any]:
    image: dict[str, Any] = {"url": "https://sns-webpic-qc.xhscdn.com/live-photo.jpg", "width": 1, "height": 1}
    if url is not None:
        image["live_photo"] = {"stream": {"h264": [{"master_url": url, "backup_urls": []}]}}
    return image


def _note(images: list[dict[str, Any]], *, note_type: str = "normal") -> dict[str, Any]:
    return {"note_id": "xhs-live-note-1", "type": note_type, "image_list": images, "video_url": ""}


def test_single_live_image_still_captures_the_v1_field() -> None:
    captured = capture_xhs_live_fields(_note([_image()]))

    assert captured == {XHS_LIVE_VIDEO_FIELD: {"url": "http://sns-video-bd.xhscdn.com/live-stream.mp4"}}


def test_two_paired_live_images_capture_the_ordered_v2_list() -> None:
    note = _note(
        [
            _image("http://sns-video-bd.xhscdn.com/first.mp4"),
            _image("http://sns-video-bd.xhscdn.com/second.mp4"),
        ]
    )

    captured = capture_xhs_live_fields(note)

    assert captured == {
        XHS_LIVE_VIDEO_LIST_FIELD: {
            "urls": ["http://sns-video-bd.xhscdn.com/first.mp4", "http://sns-video-bd.xhscdn.com/second.mp4"]
        }
    }


def test_sixteen_paired_live_images_capture_the_full_bound_list() -> None:
    images = [_image(f"http://sns-video-bd.xhscdn.com/stream-{index:02d}.mp4") for index in range(XHS_LIVE_MAX_PAIRS)]
    note = _note(images)

    captured = capture_xhs_live_fields(note)

    assert captured is not None
    urls = captured[XHS_LIVE_VIDEO_LIST_FIELD]["urls"]
    assert isinstance(urls, list)
    assert len(urls) == XHS_LIVE_MAX_PAIRS
    assert urls[0] == "http://sns-video-bd.xhscdn.com/stream-00.mp4"
    assert urls[-1] == "http://sns-video-bd.xhscdn.com/stream-15.mp4"


def test_partial_live_coverage_captures_nothing() -> None:
    note = _note([_image(), _image(url=None)])

    assert capture_xhs_live_fields(note) is None


def test_above_bound_live_list_captures_nothing() -> None:
    images = [_image(f"http://sns-video-bd.xhscdn.com/stream-{index}.mp4") for index in range(XHS_LIVE_MAX_PAIRS + 1)]
    note = _note(images)

    assert capture_xhs_live_fields(note) is None


def test_empty_image_list_captures_nothing() -> None:
    assert capture_xhs_live_fields(_note([])) is None


def test_video_type_note_captures_nothing() -> None:
    note = _note([_image(), _image()], note_type="video")

    assert capture_xhs_live_fields(note) is None


def test_malformed_nesting_captures_nothing() -> None:
    broken_live = {"url": "https://sns-webpic-qc.xhscdn.com/live-photo.jpg", "live_photo": "not-a-mapping"}
    broken_stream = {
        "url": "https://sns-webpic-qc.xhscdn.com/live-photo.jpg",
        "live_photo": {"stream": []},
    }
    empty_h264 = {
        "url": "https://sns-webpic-qc.xhscdn.com/live-photo.jpg",
        "live_photo": {"stream": {"h264": []}},
    }
    foreign_host = _image("https://evil.example.test/stream.mp4")

    for image in (broken_live, broken_stream, empty_h264, foreign_host):
        assert capture_xhs_live_fields(_note([_image(), image])) is None


def test_non_list_or_non_mapping_image_entries_capture_nothing() -> None:
    scalar_images = {"note_id": "xhs-live-note-1", "type": "normal", "image_list": "url-only", "video_url": ""}
    non_mapping_entry = _note([_image(), "https://sns-webpic-qc.xhscdn.com/second.jpg"])

    assert capture_xhs_live_fields(scalar_images) is None
    assert capture_xhs_live_fields(non_mapping_entry) is None
