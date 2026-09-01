from __future__ import annotations

import importlib
import json
import sys
import types
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar
from uuid import uuid4

import pytest

from media_sync.domain import LoginMethod, Platform
from media_sync.integrations.mediacrawler import bridge as bridge_module
from media_sync.integrations.mediacrawler import runner as runner_module
from media_sync.integrations.mediacrawler.bridge import MediaCrawlerRunMode, RunnerManifest
from media_sync.integrations.mediacrawler.policies import WatchdogLimits


def _manifest(tmp_path: Path, checkout_root: Path) -> RunnerManifest:
    integration_root = (tmp_path / "runtime").absolute()
    account_root = integration_root / "accounts" / str(uuid4())
    profile_root = account_root / "profiles" / "zhihu_user_data_dir"
    job_root = integration_root / "jobs" / str(uuid4())
    output_root = job_root / "output"
    output_root.mkdir(parents=True)
    identity = uuid4()
    return RunnerManifest(
        checkout_root=checkout_root,
        lock_path=(tmp_path / "upstreams.lock.json").absolute(),
        python_executable=Path(sys.executable).resolve(),
        integration_root=integration_root,
        account_id=uuid4(),
        subscription_id=uuid4(),
        job_id=identity,
        checkpoint_revision_before=0,
        intended_mode=MediaCrawlerRunMode.FORWARD,
        account_root=account_root,
        profile_root=profile_root,
        job_root=job_root,
        output_root=output_root,
        upstream_sha="d6f7c5bb906b6dac40ddf343ef9e26438a3de092",
        platform=Platform.ZHIHU,
        login_method=LoginMethod.QR,
        author_remote_id_fingerprint_sha256="a" * 64,
        creator_fingerprint_sha256="b" * 64,
        allow_full_history=False,
        headless=True,
        max_items=23,
        watchdogs=WatchdogLimits(max_seconds=2, poll_seconds=0.01),
        execution_id=identity,
        sync_run_id=uuid4(),
        request_delay_seconds=0.01,
    )


def _fake_modules(checkout_root: Path) -> tuple[dict[str, types.ModuleType], type[Any]]:
    config = types.ModuleType("config")
    config.__file__ = str(checkout_root / "config" / "__init__.py")

    class Content:
        def __init__(self, content_id: str) -> None:
            self.content_id = content_id
            self.question_id = "202"
            self.content_type = "answer"
            self.content_url = f"https://www.zhihu.com/question/202/answer/{content_id}"

        def model_dump(self) -> dict[str, object]:
            return {
                "content_id": self.content_id,
                "question_id": self.question_id,
                "content_type": self.content_type,
                "content_url": self.content_url,
            }

    class Extractor:
        def _extract_answer_content(self, answer: Mapping[str, object]) -> Content:
            return Content(str(answer["id"]))

        def extract_content_list_from_creator(self, data: list[object]) -> list[Content]:
            return [Content(str(item)) for item in data]

    class JsonlStore:
        async def store_content(self, content_item: Mapping[str, object]) -> None:
            target = Path(config.SAVE_DATA_PATH) / "zhihu" / "jsonl" / "creator_contents_fixture.jsonl"
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(dict(content_item), separators=(",", ":")) + "\n")

    async def update_zhihu_content(content_item: Content) -> None:
        await JsonlStore().store_content(content_item.model_dump())

    class Client:
        calls: ClassVar[list[tuple[str, int, int]]] = []

        def __init__(self) -> None:
            self._extractor = Extractor()

        async def get_creator_answers(self, url_token: str, offset: int, limit: int) -> dict[str, object]:
            type(self).calls.append((url_token, offset, limit))
            return {"data": list(range(offset + 1, offset + limit + 1)), "paging": {"is_end": False}}

        async def get_all_anwser_by_creator(
            self,
            url_token: str,
            crawl_interval: float = 1.0,
            callback: Any = None,
        ) -> list[Content]:
            del url_token, crawl_interval, callback
            raise AssertionError("the scheduled child must install the bounded Zhihu method")

    help_module = types.ModuleType("media_platform.zhihu.help")
    help_module.__file__ = str(checkout_root / "media_platform" / "zhihu" / "help.py")
    help_module.ZhihuExtractor = Extractor
    client_module = types.ModuleType("media_platform.zhihu.client")
    client_module.__file__ = str(checkout_root / "media_platform" / "zhihu" / "client.py")
    client_module.ZhiHuClient = Client
    store_module = types.ModuleType("store.zhihu")
    store_module.__file__ = str(checkout_root / "store" / "zhihu" / "__init__.py")
    store_module.ZhihuJsonlStoreImplement = JsonlStore
    store_module.update_zhihu_content = update_zhihu_content
    store_impl_module = types.ModuleType("store.zhihu._store_impl")
    store_impl_module.__file__ = str(checkout_root / "store" / "zhihu" / "_store_impl.py")
    store_impl_module.ZhihuJsonlStoreImplement = JsonlStore

    main = types.ModuleType("main")
    main.__file__ = str(checkout_root / "main.py")

    async def run_main() -> None:
        assert config.PLATFORM == "zhihu"
        assert config.CRAWLER_TYPE == "creator"
        assert config.CRAWLER_MAX_NOTES_COUNT == 23
        assert config.ZHIHU_CREATOR_URL_LIST == ["https://www.zhihu.com/people/creator-token"]

        async def store_page(contents: list[Content]) -> None:
            for content in contents:
                await store_module.update_zhihu_content(content)

        await Client().get_all_anwser_by_creator(
            "creator-token",
            crawl_interval=config.CRAWLER_MAX_SLEEP_SEC,
            callback=store_page,
        )

    main.main = run_main
    modules = {
        "config": config,
        "main": main,
        "media_platform.zhihu.help": help_module,
        "media_platform.zhihu.client": client_module,
        "store.zhihu": store_module,
        "store.zhihu._store_impl": store_impl_module,
    }
    return modules, Client


async def test_scheduled_child_bounds_real_creator_callback_and_output_to_manifest_max_items(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout_root = (tmp_path / "MediaCrawler").absolute()
    checkout_root.mkdir()
    manifest = _manifest(tmp_path, checkout_root)
    modules, client_class = _fake_modules(checkout_root)
    original_import = importlib.import_module

    def import_module(name: str, package: str | None = None) -> types.ModuleType:
        candidate = modules.get(name)
        return candidate if candidate is not None else original_import(name, package)

    monkeypatch.setattr(importlib, "import_module", import_module)
    monkeypatch.setattr(
        bridge_module,
        "verify_manifest_checkout",
        lambda _manifest: SimpleNamespace(root=checkout_root),
    )
    monkeypatch.setattr(runner_module.os, "chdir", lambda _root: None)
    monkeypatch.setattr(runner_module.sys, "path", [str(checkout_root), *sys.path])
    monkeypatch.setattr(runner_module.sys, "argv", ["pytest"])
    monkeypatch.delitem(sys.modules, "config", raising=False)
    monkeypatch.delitem(sys.modules, "main", raising=False)

    returncode = await runner_module._execute_child(
        manifest,
        "https://www.zhihu.com/people/creator-token",
        None,
        None,
    )

    output = next(manifest.output_root.rglob("*.jsonl"))
    rows = [json.loads(line) for line in output.read_text("utf-8").splitlines()]
    assert returncode == 0
    assert [row["content_id"] for row in rows] == [str(item) for item in range(1, 24)]
    assert client_class.calls == [("creator-token", 0, 20), ("creator-token", 20, 3)]
    assert modules["config"].COOKIES == ""
