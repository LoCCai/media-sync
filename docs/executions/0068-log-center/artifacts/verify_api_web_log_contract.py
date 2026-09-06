"""Re-run the real offline API -> TypeScript log-center contract.

Run from the repository root:
    uv run --no-sync python docs/executions/0068-log-center/artifacts/verify_api_web_log_contract.py

Requires the existing Python development environment, Node.js and installed
web dependencies. This intentionally imports the repository's synthetic HTTP
test fixtures and loads the actual frontend modules, not hand-written response
fixtures. SQLite, log segments and the synthetic operator credential live only
in an automatically cleaned system temporary directory. Complete responses
travel to Node through stdin; neither responses nor credentials are printed or
written into the repository. No platform/network qualification is performed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path


def main() -> int:
    repository = Path(__file__).resolve().parents[4]
    helper = Path(__file__).with_suffix(".cjs")
    node = shutil.which("node")
    if node is None or not (repository / "web/node_modules/typescript").is_dir():
        print('{"runtime_contract":"FAILED","reason":"node_or_web_dependencies_unavailable"}')
        return 1

    sys.path.insert(0, str(repository / "tests/unit"))
    sys.path.insert(0, str(repository / "src"))
    # The known Starlette/httpx deprecation warning is unrelated to this
    # contract. Keep the successful machine-readable output deterministic.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated.*")
        from _api_client import authenticated_test_client
        from fastapi.testclient import TestClient
        from test_log_center_api import PRIVATE, _seed, _settings, _stage

    with tempfile.TemporaryDirectory(prefix="media-sync-log-contract-") as directory:
        settings = _settings(Path(directory))
        operation_id, account_id, session_id = _seed(settings, controls=201, subjects=65)
        with authenticated_test_client(settings) as client:
            store = client.app.state.log_store
            assert store.emit(_stage(operation_id, account_id, session_id))
            assert store.flush()
            page = client.get("/api/v1/logs", params={"operation_id": operation_id})
            status = client.get("/api/v1/logs/status")
            trace = client.get(f"/api/v1/logs/operations/{operation_id}")
            diagnostic = client.get(f"/api/v1/logs/operations/{operation_id}/diagnostic")
            responses = (page, status, trace, diagnostic)
            assert all(response.status_code == 200 for response in responses)
            assert all(response.headers.get("cache-control") == "no-store" for response in responses)
            assert all(PRIVATE not in response.text for response in responses)
            assert len(diagnostic.content) <= 1_048_576
            assert diagnostic.headers["content-type"] == "application/json"
            assert diagnostic.headers["content-disposition"] == (
                f'attachment; filename="media-sync-diagnostic-{operation_id}.json"'
            )

            # Reuse the started ASGI app without inheriting the authenticated
            # client's cookie jar or invoking a second lifespan.
            anonymous = TestClient(client.app, base_url="http://127.0.0.1:8632", follow_redirects=False)
            try:
                auth_codes = [
                    anonymous.get(path).status_code
                    for path in (
                        "/api/v1/logs",
                        "/api/v1/logs/status",
                        f"/api/v1/logs/operations/{operation_id}",
                        f"/api/v1/logs/operations/{operation_id}/diagnostic",
                    )
                ]
                assert auth_codes == [401] * 4
                for destination in ("logs", "jobs"):
                    response = anonymous.get(f"/{destination}", headers={"Accept": "text/html"})
                    assert response.status_code == 303
                    assert response.headers["location"] == f"/?return_to=%2F{destination}"
            finally:
                anonymous.close()

            contract = {
                "operation_id": operation_id,
                "page": page.json(),
                "status": status.json(),
                "trace": trace.json(),
                "diagnostic": diagnostic.json(),
                "private_sentinel": PRIVATE,
            }
            result = subprocess.run(
                [node, str(helper)],
                input=json.dumps(contract, ensure_ascii=True),
                text=True,
                capture_output=True,
                cwd=repository,
                timeout=30,
                check=False,
            )
            # Never echo complete Node assertion diagnostics: they could
            # contain a rejected response value. Node emits fixed summaries.
            if result.returncode != 0:
                print('{"runtime_contract":"FAILED","reason":"frontend_contract_rejected"}')
                return 1
            summary = json.loads(result.stdout)
            expected = {
                "runtime_contract": "PASS",
                "authenticated_api": "200_no_store",
                "anonymous_api": "401_all_four",
                "anonymous_pages": "303_logs_and_jobs",
                "login_return": "logs_accepted",
                "events": 1,
                "control_events": 200,
                "subjects": 64,
                "truncation_flags": "preserved",
                "microseconds": "preserved",
                "writer_health": "preserved",
                "diagnostic_limits": "backend_1MiB_frontend_2MiB",
                "private_fields": "absent",
            }
            assert summary == expected
            print(json.dumps(expected, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception:
        # A stable failure code is safer than printing a raw assertion or
        # traceback containing temporary filesystem paths or response values.
        print('{"runtime_contract":"FAILED","reason":"offline_contract_check_failed"}')
        exit_code = 1
    raise SystemExit(exit_code)
