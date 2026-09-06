"""Real script workers preserve platform dispatch and typed failure identity offline."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

from media_sync.integrations.mediacrawler import cookie_login_runner as runner

_HARNESS = r"""
import builtins
import hashlib
import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys

script, platform, outcome, cookie_digest = sys.argv[1:]
original_import = builtins.__import__
hits = []
forbidden_calls = []
targets = {
    "media_sync.integrations.mediacrawler.douyin_cookie_login":
        ("dy", "verify_douyin_cookie"),
    "media_sync.integrations.mediacrawler.kuaishou_cookie_login":
        ("ks", "verify_kuaishou_cookie"),
}

def forbidden(*args, **kwargs):
    forbidden_calls.append(True)
    raise AssertionError("external work is forbidden in worker dispatch coverage")

def import_platform(name, globals=None, locals=None, fromlist=(), level=0):
    if name in targets:
        # Guard before importing or invoking either platform adapter. The
        # standard-library Windows event loop has already made its own local
        # socket pair; it is not a platform request and remains unmodified.
        socket.getaddrinfo = forbidden
        socket.create_connection = forbidden
        socket.socket.connect = forbidden
        socket.socket.connect_ex = forbidden
        socket.socket.sendto = forbidden
        subprocess.Popen.__init__ = forbidden
    module = original_import(name, globals, locals, fromlist, level)
    if name in targets and targets[name][1] in fromlist:
        # Import the real platform module (including its canonical shared
        # exception), replacing only external validation work.
        from media_sync.integrations.mediacrawler import cookie_login_runner as core
        target_platform, function = targets[name]
        assert callable(getattr(module, function))

        def verify_candidate(cookie, deadline):
            assert target_platform == platform
            assert hits == []
            hits.append(target_platform)
            assert hashlib.sha256(cookie.reveal().encode()).hexdigest() == cookie_digest
            assert 0 < deadline - __import__("time").monotonic() <= 45
            assert cookie.reveal() not in " ".join(sys.argv)
            assert cookie.reveal() not in " ".join(os.environ.values())
            # Exercise the actual worker silencer for both Python and native
            # writes. Candidate bytes must never contaminate its control frame.
            print(cookie.reveal(), flush=True)
            print(str(Path.cwd()), file=sys.stderr, flush=True)
            os.write(1, cookie.reveal().encode())
            os.write(2, cookie.reveal().encode())
            if outcome == "untyped_private_error":
                raise RuntimeError(cookie.reveal())
            if outcome != "authenticated":
                raise core._VerificationFailure(outcome)

        if target_platform == "dy":
            async def verify(cookie, deadline):
                verify_candidate(cookie, deadline)
        else:
            async def verify(checkout, request, deadline):
                assert checkout.resolve() == Path.cwd().resolve()
                assert request.platform.value == platform
                verify_candidate(request.cookie, deadline)
        setattr(module, function, verify)
    return module

builtins.__import__ = import_platform
sys.argv = [script, "--worker"]
try:
    runpy.run_path(script, run_name="__main__")
except SystemExit:
    assert hits == [platform], "selected platform validator was not called once"
    assert not forbidden_calls, "unexpected external work was attempted"
    raise
else:
    raise AssertionError("worker did not terminate with its declared entrypoint")
"""


@pytest.mark.parametrize("platform", ["dy", "ks"])
@pytest.mark.parametrize(
    "outcome",
    ["authenticated", "rejected", "timed_out", "configuration_invalid", "result_invalid", "untyped_private_error"],
)
def test_script_worker_dispatches_once_and_preserves_typed_failures_without_secret_output(
    tmp_path: Path, platform: str, outcome: str
) -> None:
    account, operation = str(uuid4()), str(uuid4())
    cookie = "session=PRIVATE_COOKIE_DISPATCH==; kuaishou.web.cp.api_ph=OFFLINE_CANDIDATE"
    payload = {
        "schema_version": runner.SCHEMA_VERSION,
        "request": {"account_id": account, "platform": platform, "operation_id": operation, "cookie": cookie},
        "checkout_root": str(tmp_path.resolve()),
        "upstream_sha": "a" * 40,
        "deadline": time.monotonic() + 40,
    }
    command = [
        sys.executable,
        "-I",
        "-u",
        "-B",
        "-c",
        _HARNESS,
        str(Path(runner.__file__).resolve()),
        platform,
        outcome,
        hashlib.sha256(cookie.encode()).hexdigest(),
    ]
    assert cookie not in " ".join(command)
    completed = subprocess.run(
        command,
        cwd=tmp_path,
        input=runner._encode(payload, runner.MAX_REQUEST_BYTES),
        capture_output=True,
        timeout=45,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert completed.stderr == b""
    assert b"PRIVATE_COOKIE_DISPATCH" not in completed.stdout
    assert b"OFFLINE_CANDIDATE" not in completed.stdout
    assert str(tmp_path).encode() not in completed.stdout
    assert list(tmp_path.iterdir()) == []
    size = int.from_bytes(completed.stdout[:4], "big")
    assert 0 < size <= runner.MAX_RESULT_BYTES
    assert size == len(completed.stdout) - 4
    assert json.loads(completed.stdout[4:]) == {
        "schema_version": runner.SCHEMA_VERSION,
        "status": "result_invalid" if outcome == "untyped_private_error" else outcome,
        "account_id": account,
        "platform": platform,
        "operation_id": operation,
        "upstream_sha": "a" * 40,
    }
