"""Wiring invariant: every delivery-progress repository is published by the worker.

Execution 0086 added `ZhihuDeliveryProgressRepository`, the Zhihu delivery
policy and the materialisation/ingestion paths, but the pipeline worker that is
the *only* publisher for the other six platforms was left without the Zhihu
calls. The row was therefore created and never advanced: `phase` stayed
`backfill` forever and a terminal pipeline failure never set `blocked_code`.

`test_zhihu_creator_answers_delivery.py` could not catch it because it calls the
repository directly, bypassing the worker — which is exactly how the gap
survived a green suite. This module pins the invariant at its source: for every
platform that owns a delivery-progress table, the worker must publish both the
success and the terminal-failure transition.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from media_sync.scheduler import (
    bili_delivery_progress,
    douyin_delivery_progress,
    kuaishou_delivery_progress,
    pipeline_worker,
    tieba_delivery_progress,
    weibo_delivery_progress,
    xhs_delivery_progress,
    zhihu_delivery_progress,
)

PROGRESS_MODULES = {
    "bili": bili_delivery_progress,
    "xhs": xhs_delivery_progress,
    "douyin": douyin_delivery_progress,
    "kuaishou": kuaishou_delivery_progress,
    "weibo": weibo_delivery_progress,
    "tieba": tieba_delivery_progress,
    "zhihu": zhihu_delivery_progress,
}


def _repository_classes() -> dict[str, str]:
    """Map platform name to its `*DeliveryProgressRepository` class name."""

    result: dict[str, str] = {}
    for platform, module in PROGRESS_MODULES.items():
        names = [name for name in dir(module) if name.endswith("DeliveryProgressRepository")]
        assert len(names) == 1, (platform, names)
        result[platform] = names[0]
    return result


def test_every_platform_delivery_repository_is_published_by_the_worker() -> None:
    classes = _repository_classes()

    assert set(classes) == {"bili", "xhs", "douyin", "kuaishou", "weibo", "tieba", "zhihu"}

    source = inspect.getsource(pipeline_worker)
    missing_success = [
        platform for platform, name in classes.items() if f"{name}(session).publish_success(" not in source
    ]
    missing_failure = [
        platform for platform, name in classes.items() if f"{name}(session).publish_terminal_failure(" not in source
    ]

    assert missing_success == [], f"pipeline worker never publishes success for {missing_success}"
    assert missing_failure == [], f"pipeline worker never publishes terminal failure for {missing_failure}"


def test_every_platform_delivery_policy_is_constructed_in_the_worker() -> None:
    """A published repository without its policy would raise on an unset SHA."""

    source = inspect.getsource(pipeline_worker)
    for platform in PROGRESS_MODULES:
        assert re.search(rf"self\.{platform}_delivery_policy = ", source), platform


@pytest.mark.parametrize("platform", sorted(PROGRESS_MODULES))
def test_every_delivery_module_exposes_both_publish_transitions(platform: str) -> None:
    module = PROGRESS_MODULES[platform]
    classes = [getattr(module, name) for name in dir(module) if name.endswith("DeliveryProgressRepository")]

    assert len(classes) == 1
    repository = classes[0]
    assert callable(getattr(repository, "publish_success", None)), platform
    assert callable(getattr(repository, "publish_terminal_failure", None)), platform


def test_worker_module_path_is_the_expected_one() -> None:
    """Guard the `inspect`-based checks above against a moved module."""

    assert Path(pipeline_worker.__file__).name == "pipeline_worker.py"
