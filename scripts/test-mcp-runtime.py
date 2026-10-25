"""Real process protocol check; no account login, page navigation or publication."""

import asyncio, json, hashlib, os
from pathlib import Path
from app.config import ROOT

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(ROOT / ".local" / "browsers")
os.environ.setdefault(
    "PUB_XHS_BINARY",
    str(
        ROOT
        / ".local"
        / ("xiaohongshu-mcp.exe" if os.name == "nt" else "xiaohongshu-mcp")
    ),
)
import sys

sys.path.insert(0, str(ROOT))
from publisher.xhs_runtime import Runtime
from playwright.async_api import async_playwright


async def main():
    state = {}
    runtime = Runtime(state.get, lambda k, v: state.__setitem__(k, v))
    async with async_playwright() as p:
        runtime.executable = p.chromium.executable_path
        if not Path(runtime.executable).is_file():
            raise SystemExit(
                "Install Python Playwright Chromium into .local/browsers first"
            )
        try:
            first = await runtime.ensure("protocol-account-a")
            second = await runtime.ensure("protocol-account-b")
            tools = await asyncio.to_thread(first["client"].tools)
            assert (
                first["client"].url != second["client"].url
                and first["cookie"] != second["cookie"]
            )
            assert any(t["name"] == "publish_content" for t in tools)
            report = {
                "status": "passed",
                "real_processes": 2,
                "account_isolation": True,
                "mcp_handshake": True,
                "tool_discovery": True,
                "account_login": False,
                "real_publish": False,
                "binary_sha256": hashlib.sha256(
                    Path(os.environ["PUB_XHS_BINARY"]).read_bytes()
                ).hexdigest(),
            }
            (ROOT / "docs" / "xhs-runtime-report.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            print(json.dumps(report))
        finally:
            await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())
