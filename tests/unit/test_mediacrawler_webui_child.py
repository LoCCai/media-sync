from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from media_sync.integrations.mediacrawler.webui_child import (
    _apply_zhihu_creator_compatibility,
    run,
)


def test_zhihu_creator_compatibility_mirrors_pinned_cli_list_parsing() -> None:
    config = SimpleNamespace(
        ZHIHU_CREATOR_URL_LIST=["zhihu-default"],
        XHS_CREATOR_ID_LIST=["xhs-default"],
        BILI_CREATOR_ID_LIST=["bili-default"],
        DY_CREATOR_ID_LIST=["dy-default"],
        WEIBO_CREATOR_ID_LIST=["weibo-default"],
        KS_CREATOR_ID_LIST=["ks-default"],
        TIEBA_CREATOR_URL_LIST=["tieba-default"],
    )
    arguments = [
        "--platform",
        "zhihu",
        "--type",
        "creator",
        "--creator_id",
        " creator-token, https://www.zhihu.com/people/second-token, ,third-token ",
        "--headless",
        "false",
    ]
    original_arguments = list(arguments)

    _apply_zhihu_creator_compatibility(config, arguments)

    assert config.ZHIHU_CREATOR_URL_LIST == [
        "creator-token",
        "https://www.zhihu.com/people/second-token",
        "third-token",
    ]
    assert config.XHS_CREATOR_ID_LIST == ["xhs-default"]
    assert config.BILI_CREATOR_ID_LIST == ["bili-default"]
    assert config.DY_CREATOR_ID_LIST == ["dy-default"]
    assert config.WEIBO_CREATOR_ID_LIST == ["weibo-default"]
    assert config.KS_CREATOR_ID_LIST == ["ks-default"]
    assert config.TIEBA_CREATOR_URL_LIST == ["tieba-default"]
    assert arguments == original_arguments


@pytest.mark.parametrize(
    ("platform", "crawler_type", "creator_id"),
    [
        ("xhs", "creator", "xhs-creator"),
        ("dy", "creator", "dy-creator"),
        ("ks", "creator", "ks-creator"),
        ("bili", "creator", "252671524"),
        ("wb", "creator", "weibo-creator"),
        ("tieba", "creator", "tieba-creator"),
        ("zhihu", "detail", "zhihu-detail"),
        ("zhihu", "creator", ""),
    ],
)
def test_zhihu_creator_compatibility_does_not_change_other_argument_shapes(
    platform: str,
    crawler_type: str,
    creator_id: str,
) -> None:
    config = SimpleNamespace(ZHIHU_CREATOR_URL_LIST=["fixture-default"])
    arguments = [
        "--platform",
        platform,
        "--type",
        crawler_type,
        "--creator_id",
        creator_id,
    ]

    _apply_zhihu_creator_compatibility(config, arguments)

    assert config.ZHIHU_CREATOR_URL_LIST == ["fixture-default"]


def test_child_applies_zhihu_creator_compatibility_before_upstream_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = tmp_path / "checkout"
    (checkout / "config").mkdir(parents=True)
    (checkout / "tools").mkdir()
    (checkout / "config" / "__init__.py").write_text(
        "ZHIHU_CREATOR_URL_LIST = ['fixture-default']\nBILI_CREATOR_ID_LIST = ['bili-default']\n",
        encoding="utf-8",
    )
    (checkout / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (checkout / "tools" / "utils.py").write_text(
        "def show_qrcode(_value):\n    return None\n",
        encoding="utf-8",
    )
    (checkout / "tools" / "app_runner.py").write_text(
        "import asyncio\n"
        "def run(main, cleanup, **_kwargs):\n"
        "    async def execute():\n"
        "        try:\n"
        "            await main()\n"
        "        finally:\n"
        "            await cleanup()\n"
        "    asyncio.run(execute())\n",
        encoding="utf-8",
    )
    result = tmp_path / "result.json"
    (checkout / "main.py").write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "import config\n"
        "class DummyCrawler:\n"
        "    async def launch_browser(self, chromium, **kwargs):\n"
        "        return chromium, kwargs\n"
        "class CrawlerFactory:\n"
        "    @staticmethod\n"
        "    def create_crawler(_platform):\n"
        "        return DummyCrawler()\n"
        "async def main():\n"
        "    Path(os.environ['MEDIA_SYNC_TEST_RESULT']).write_text(json.dumps({\n"
        "        'zhihu': config.ZHIHU_CREATOR_URL_LIST,\n"
        "        'bili': config.BILI_CREATOR_ID_LIST,\n"
        "        'argv': sys.argv,\n"
        "    }), encoding='utf-8')\n"
        "async def async_cleanup():\n"
        "    return None\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MEDIA_SYNC_TEST_RESULT", str(result))
    qr_path = tmp_path / "runtime" / "webui-login-qr.png"
    arguments = [
        "--checkout",
        str(checkout),
        "--output-root",
        str(tmp_path / "runtime" / "webui-output"),
        "--profile-root",
        str(tmp_path / "runtime" / "webui-profiles"),
        "--qr-path",
        str(qr_path),
        "--",
        "--platform",
        "zhihu",
        "--type",
        "creator",
        "--creator_id",
        " first-token,https://www.zhihu.com/people/second-token ",
    ]
    previous_cwd = Path.cwd()
    previous_argv = sys.argv
    previous_path = list(sys.path)
    module_names = ("config", "main", "tools", "tools.utils", "tools.app_runner")
    removed = {name: sys.modules.pop(name, None) for name in module_names}
    try:
        run(arguments)
    finally:
        os.chdir(previous_cwd)
        sys.argv = previous_argv
        sys.path[:] = previous_path
        for name in module_names:
            sys.modules.pop(name, None)
        sys.modules.update({name: module for name, module in removed.items() if module is not None})

    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["zhihu"] == [
        "first-token",
        "https://www.zhihu.com/people/second-token",
    ]
    assert payload["bili"] == ["bili-default"]
    assert payload["argv"][payload["argv"].index("--creator_id") + 1] == (
        " first-token,https://www.zhihu.com/people/second-token "
    )
