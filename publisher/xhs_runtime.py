"""An account owns a process, cookie file, token and encrypted state."""

import asyncio, base64, json, os, secrets, socket, tempfile
from pathlib import Path
from .mcp_client import Client, MCPError


class Runtime:
    def __init__(self, read, write):
        self.read = read
        self.write = write
        self.accounts = {}
        self.lifecycle_lock = asyncio.Lock()
        self.busy = set()
        self.max_active = max(1, int(os.environ.get("PUB_XHS_MAX_ACTIVE", "2")))
        self.slots = asyncio.Semaphore(self.max_active)
        self.executable = ""

    async def ensure(self, account):
        if (
            account in self.accounts
            and self.accounts[account]["process"].returncode is None
        ):
            return self.accounts[account]
        binary = Path(
            os.environ.get("PUB_XHS_BINARY", "/usr/local/bin/xiaohongshu-mcp")
        )
        if not binary.is_file():
            raise MCPError("XHS_BINARY_UNCONFIGURED")
        directory = Path(
            tempfile.mkdtemp(
                prefix="xhs-",
                dir=os.environ.get("PUB_EPHEMERAL_DIR", tempfile.gettempdir()),
            )
        )
        directory.chmod(0o700)
        cookie = directory / "cookies.json"
        saved = self.read("xhs-cookie-" + account)
        if saved:
            cookie.write_bytes(base64.b64decode(saved["data"]))
            cookie.chmod(0o600)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        token = secrets.token_hex(32)
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            in (
                "PATH",
                "HOME",
                "TMPDIR",
                "TEMP",
                "TMP",
                "SYSTEMROOT",
                "WINDIR",
                "SSL_CERT_FILE",
                "SSL_CERT_DIR",
            )
        }
        env.update(
            TMPDIR=str(directory),
            TEMP=str(directory),
            TMP=str(directory),
            COOKIES_PATH=str(cookie),
            AUTH_TOKEN=token,
            OPS_MANAGED_CHROMIUM=self.executable
            or os.environ.get("PUB_CHROMIUM_BIN", ""),
        )
        process = await asyncio.create_subprocess_exec(
            str(binary),
            "-port",
            f"127.0.0.1:{port}",
            env=env,
            cwd=directory,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        client = Client(
            f"http://127.0.0.1:{port}/mcp",
            {"Authorization": "Bearer " + token},
            timeout=300,
        )
        state = {
            "directory": directory,
            "cookie": cookie,
            "process": process,
            "client": client,
        }
        self.accounts[account] = state
        for _ in range(60):
            if process.returncode is not None:
                raise MCPError("XHS_PROCESS_FAILED")
            try:
                await asyncio.to_thread(client.initialize)
                return state
            except (OSError, httpx.HTTPError, MCPError):
                await asyncio.sleep(1)
        raise MCPError("XHS_STARTUP_TIMEOUT")

    async def call(self, account, name, args):
        async with self.slots:
            async with self.lifecycle_lock:
                if account not in self.accounts and len(self.accounts) >= self.max_active:
                    idle = next((a for a in self.accounts if a not in self.busy), None)
                    if idle is not None:
                        await self.retire(idle)
                state = await self.ensure(account)
                self.busy.add(account)
            try:
                return await asyncio.to_thread(state["client"].call, name, args)
            finally:
                self.sync(account)
                self.busy.discard(account)

    async def retire(self, account):
        import shutil
        state = self.accounts.get(account)
        if not state or account in self.busy:
            return
        self.sync(account)
        if state["process"].returncode is None:
            state["process"].terminate()
            try:
                await asyncio.wait_for(state["process"].wait(), 5)
            except asyncio.TimeoutError:
                state["process"].kill()
                await state["process"].wait()
        # The temporary directory is allocated by this runtime, never supplied by a tenant.
        folder = state["directory"].resolve()
        expected = Path(os.environ.get("PUB_EPHEMERAL_DIR", tempfile.gettempdir())).resolve()
        if folder.parent != expected or not folder.name.startswith("xhs-"):
            raise MCPError("XHS_TEMP_PATH_INVALID")
        shutil.rmtree(folder)
        self.accounts.pop(account, None)

    def sync(self, account):
        state = self.accounts.get(account)
        if state and state["cookie"].is_file():
            self.write(
                "xhs-cookie-" + account,
                {"data": base64.b64encode(state["cookie"].read_bytes()).decode()},
            )

    async def close(self):
        import shutil

        for account, state in self.accounts.items():
            self.sync(account)
            if state["process"].returncode is None:
                state["process"].terminate()
                try:
                    await asyncio.wait_for(state["process"].wait(), 5)
                except asyncio.TimeoutError:
                    state["process"].kill()
                    await state["process"].wait()
            folder = state["directory"].resolve()
            expected = Path(os.environ.get("PUB_EPHEMERAL_DIR", tempfile.gettempdir())).resolve()
            if folder.parent != expected or not folder.name.startswith("xhs-"):
                raise MCPError("XHS_TEMP_PATH_INVALID")
            shutil.rmtree(folder)
        self.accounts.clear()


import httpx
