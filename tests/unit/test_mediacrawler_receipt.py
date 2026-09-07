"""Focused identity comparison coverage for sealed MediaCrawler output."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

import media_sync.integrations.mediacrawler.receipt as receipt_module


def test_windows_signature_tolerates_only_delayed_ctime_flush(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = receipt_module._FileSignature(1, 2, 0o100600, 1, 23, 4, 5)
    monkeypatch.setattr(receipt_module, "os", SimpleNamespace(name="nt"))

    assert receipt_module._stable_signature_equal(baseline, replace(baseline, changed_ns=6))
    for field in ("device", "inode", "mode", "links", "size", "modified_ns"):
        assert not receipt_module._stable_signature_equal(
            baseline,
            replace(baseline, **{field: getattr(baseline, field) + 1}),
        )


def test_posix_signature_keeps_ctime_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = receipt_module._FileSignature(1, 2, 0o100600, 1, 23, 4, 5)
    monkeypatch.setattr(receipt_module, "os", SimpleNamespace(name="posix"))

    assert not receipt_module._stable_signature_equal(baseline, replace(baseline, changed_ns=6))
