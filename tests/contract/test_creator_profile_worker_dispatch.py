"""Real script-mode worker imports share DTO/exception identity with platform modules."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

from media_sync.integrations.mediacrawler import creator_profile_runner as runner

_HARNESS = r"""
import builtins
import runpy
import sys

script, outcome = sys.argv[1:]
original_import = builtins.__import__
targets = {
    "media_sync.integrations.mediacrawler.kuaishou_creator_profile": "lookup_kuaishou",
    "media_sync.integrations.mediacrawler.zhihu_creator_profile": "lookup_zhihu",
}
def import_platform(name, globals=None, locals=None, fromlist=(), level=0):
    module = original_import(name, globals, locals, fromlist, level)
    if name in targets and targets[name] in fromlist:
        # Load the actual platform module and its canonical shared contracts,
        # replacing only external lookup work. No browser/network is invoked.
        from media_sync.integrations.mediacrawler import creator_profile_runner as core
        async def lookup(checkout, profile, remote_id, deadline, *, cookie=None):
            if cookie is None or cookie.reveal() != "d_c0=PRIVATE_DISPATCH==; token=synthetic":
                raise AssertionError("candidate changed")
            if outcome == "result_invalid":
                raise core._LookupFailure(core.MediaCrawlerCreatorProfileStatus.RESULT_INVALID)
            return core.MediaCrawlerCreatorProfile(remote_id, "Offline nickname", None)
        setattr(module, targets[name], lookup)
    return module
builtins.__import__ = import_platform
sys.argv = [script, "--worker"]
runpy.run_path(script, run_name="__main__")
"""


@pytest.mark.parametrize("platform,remote_id", [("ks", "3xSynthetic"), ("zhihu", "test-user")])
@pytest.mark.parametrize("outcome", ["succeeded", "result_invalid"])
def test_script_worker_platform_dto_and_exception_match_parent_contract(
    tmp_path: Path, platform: str, remote_id: str, outcome: str
) -> None:
    account, operation = str(uuid4()), str(uuid4())
    payload = {
        "schema_version": runner.CREATOR_PROFILE_SCHEMA_VERSION,
        "request": {
            "account_id": account,
            "platform": platform,
            "creator_remote_id": remote_id,
            "request_id": operation,
            "cookie": "d_c0=PRIVATE_DISPATCH==; token=synthetic",
        },
        "checkout_root": str(tmp_path.resolve()),
        "upstream_sha": "a" * 40,
        "integration_root": str(tmp_path / "runtime"),
        "execution_id": str(uuid4()),
        "deadline": time.monotonic() + 40,
    }
    completed = subprocess.run(
        [sys.executable, "-I", "-u", "-B", "-c", _HARNESS, str(Path(runner.__file__).resolve()), outcome],
        cwd=tmp_path,
        input=runner._encode(payload, runner.MAX_PROFILE_REQUEST_BYTES),
        capture_output=True,
        timeout=45,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert b"PRIVATE_DISPATCH" not in completed.stdout + completed.stderr
    size = int.from_bytes(completed.stdout[:4], "big")
    assert size == len(completed.stdout) - 4
    observed = json.loads(completed.stdout[4:])
    assert observed["status"] == outcome, observed
    assert (observed["platform"], observed["creator_remote_id"], observed["request_id"]) == (
        platform,
        remote_id,
        operation,
    )
    assert observed["profile"] == (
        {"remote_id": remote_id, "display_name": "Offline nickname", "avatar_url": None}
        if outcome == "succeeded"
        else None
    )
