import os
import io
import re
import glob as glob_module
import uuid
import asyncio
import logging
import subprocess
from typing import Optional, BinaryIO, Dict, List
from async_lru import alru_cache
from app.domain.models.tool_result import ToolResult
from app.domain.external.sandbox import Sandbox
from app.domain.external.browser import Browser

logger = logging.getLogger(__name__)

SANDBOX_WORKDIR = "/home/runner/workspace/sandbox_workspace"


class LocalShellSession:
    def __init__(self, session_id: str, exec_dir: str):
        self.session_id = session_id
        self.exec_dir = exec_dir
        self.process: Optional[asyncio.subprocess.Process] = None
        self.output_lines: List[str] = []
        self.console_lines: List[str] = []
        self._running = False

    async def exec_command(self, command: str, exec_dir: str = None) -> ToolResult:
        workdir = exec_dir or self.exec_dir or SANDBOX_WORKDIR
        os.makedirs(workdir, exist_ok=True)

        try:
            self.process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=workdir,
                env={**os.environ, "HOME": SANDBOX_WORKDIR},
            )
            self._running = True

            stdout, _ = await asyncio.wait_for(
                self.process.communicate(), timeout=120
            )

            output = stdout.decode("utf-8", errors="replace") if stdout else ""
            self.output_lines = output.splitlines()
            self.console_lines.extend(self.output_lines)
            if len(self.console_lines) > 500:
                self.console_lines = self.console_lines[-500:]

            self._running = False

            return ToolResult(
                success=self.process.returncode == 0,
                message=f"Exit code: {self.process.returncode}",
                data={
                    "output": output,
                    "exit_code": self.process.returncode,
                    "id": self.session_id,
                },
            )
        except asyncio.TimeoutError:
            if self.process:
                self.process.kill()
            self._running = False
            return ToolResult(
                success=False,
                message="Command timed out after 120 seconds",
                data={"output": "Command timed out", "exit_code": -1, "id": self.session_id},
            )
        except Exception as e:
            self._running = False
            return ToolResult(
                success=False,
                message=str(e),
                data={"output": str(e), "exit_code": -1, "id": self.session_id},
            )


class LocalSandbox:
    _sessions: Dict[str, LocalShellSession] = {}

    def __init__(self):
        self._id = f"local-sandbox-{uuid.uuid4().hex[:8]}"
        self._browser = None
        os.makedirs(SANDBOX_WORKDIR, exist_ok=True)

    @property
    def id(self) -> str:
        return self._id

    @property
    def cdp_url(self) -> str:
        return "http://localhost:9222"

    @property
    def vnc_url(self) -> str:
        return "ws://localhost:5901"

    async def ensure_sandbox(self) -> None:
        logger.info("LocalSandbox: environment ready (local mode)")

    def _get_or_create_session(self, session_id: str, exec_dir: str = None) -> LocalShellSession:
        if session_id not in self._sessions:
            self._sessions[session_id] = LocalShellSession(
                session_id=session_id,
                exec_dir=exec_dir or SANDBOX_WORKDIR,
            )
        return self._sessions[session_id]

    async def exec_command(self, session_id: str, exec_dir: str, command: str) -> ToolResult:
        session = self._get_or_create_session(session_id, exec_dir)
        return await session.exec_command(command, exec_dir)

    async def view_shell(self, session_id: str, console: bool = False) -> ToolResult:
        session = self._sessions.get(session_id)
        if not session:
            return ToolResult(success=True, data={"console": [], "running": False})
        return ToolResult(
            success=True,
            data={
                "console": session.console_lines[-100:] if console else session.output_lines[-50:],
                "running": session._running,
            },
        )

    async def wait_for_process(self, session_id: str, seconds: Optional[int] = None) -> ToolResult:
        session = self._sessions.get(session_id)
        if not session or not session.process:
            return ToolResult(success=True, message="No process running")
        try:
            await asyncio.wait_for(session.process.wait(), timeout=seconds or 30)
        except asyncio.TimeoutError:
            pass
        return ToolResult(success=True, data={"running": session._running})

    async def write_to_process(self, session_id: str, input_text: str, press_enter: bool = True) -> ToolResult:
        session = self._sessions.get(session_id)
        if not session or not session.process or not session.process.stdin:
            return ToolResult(success=False, message="No running process to write to")
        text = input_text + ("\n" if press_enter else "")
        session.process.stdin.write(text.encode())
        await session.process.stdin.drain()
        return ToolResult(success=True)

    async def kill_process(self, session_id: str) -> ToolResult:
        session = self._sessions.get(session_id)
        if session and session.process:
            try:
                session.process.kill()
            except ProcessLookupError:
                pass
            session._running = False
        return ToolResult(success=True, message="Process killed")

    async def file_write(self, file: str, content: str, append: bool = False,
                         leading_newline: bool = False, trailing_newline: bool = False,
                         sudo: bool = False) -> ToolResult:
        try:
            target = self._resolve_path(file)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            final = content
            if leading_newline:
                final = "\n" + final
            if trailing_newline:
                final = final + "\n"
            mode = "a" if append else "w"
            with open(target, mode, encoding="utf-8") as f:
                f.write(final)
            return ToolResult(success=True, message=f"File written: {file}")
        except Exception as e:
            return ToolResult(success=False, message=str(e))

    async def file_read(self, file: str, start_line: int = None,
                        end_line: int = None, sudo: bool = False) -> ToolResult:
        try:
            target = self._resolve_path(file)
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            if start_line is not None or end_line is not None:
                s = start_line or 0
                e = end_line or len(lines)
                lines = lines[s:e]
            content = "".join(lines)
            return ToolResult(success=True, data={"content": content, "line_count": len(lines)})
        except FileNotFoundError:
            return ToolResult(success=False, message=f"File not found: {file}")
        except Exception as e:
            return ToolResult(success=False, message=str(e))

    async def file_exists(self, path: str) -> ToolResult:
        target = self._resolve_path(path)
        return ToolResult(success=True, data={"exists": os.path.exists(target)})

    async def file_delete(self, path: str) -> ToolResult:
        try:
            target = self._resolve_path(path)
            if os.path.isfile(target):
                os.remove(target)
            elif os.path.isdir(target):
                import shutil
                shutil.rmtree(target)
            return ToolResult(success=True, message=f"Deleted: {path}")
        except Exception as e:
            return ToolResult(success=False, message=str(e))

    async def file_list(self, path: str) -> ToolResult:
        try:
            target = self._resolve_path(path)
            entries = []
            for entry in os.listdir(target):
                full = os.path.join(target, entry)
                entries.append({
                    "name": entry,
                    "type": "directory" if os.path.isdir(full) else "file",
                    "size": os.path.getsize(full) if os.path.isfile(full) else 0,
                })
            return ToolResult(success=True, data=entries)
        except Exception as e:
            return ToolResult(success=False, message=str(e))

    async def file_replace(self, file: str, old_str: str, new_str: str,
                           sudo: bool = False) -> ToolResult:
        try:
            target = self._resolve_path(file)
            with open(target, "r", encoding="utf-8") as f:
                content = f.read()
            if old_str not in content:
                return ToolResult(success=False, message="String not found in file")
            content = content.replace(old_str, new_str, 1)
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(success=True, message="String replaced successfully")
        except Exception as e:
            return ToolResult(success=False, message=str(e))

    async def file_search(self, file: str, regex: str, sudo: bool = False) -> ToolResult:
        try:
            target = self._resolve_path(file)
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            matches = []
            pattern = re.compile(regex)
            for i, line in enumerate(lines):
                if pattern.search(line):
                    matches.append({"line": i + 1, "content": line.rstrip()})
            return ToolResult(success=True, data={"matches": matches, "count": len(matches)})
        except Exception as e:
            return ToolResult(success=False, message=str(e))

    async def file_find(self, path: str, glob_pattern: str) -> ToolResult:
        try:
            target = self._resolve_path(path)
            pattern = os.path.join(target, "**", glob_pattern)
            found = glob_module.glob(pattern, recursive=True)
            return ToolResult(success=True, data={"files": found[:100], "count": len(found)})
        except Exception as e:
            return ToolResult(success=False, message=str(e))

    async def file_upload(self, file_data: BinaryIO, path: str, filename: str = None) -> ToolResult:
        try:
            target = self._resolve_path(path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            content = file_data.read()
            with open(target, "wb") as f:
                f.write(content)
            return ToolResult(success=True, message=f"File uploaded to {path}")
        except Exception as e:
            return ToolResult(success=False, message=str(e))

    async def file_download(self, path: str) -> BinaryIO:
        target = self._resolve_path(path)
        with open(target, "rb") as f:
            content = f.read()
        return io.BytesIO(content)

    async def get_browser(self) -> Browser:
        from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser
        if not self._browser:
            self._browser = PlaywrightBrowser(cdp_url=None)
        return self._browser

    async def destroy(self) -> bool:
        try:
            for session in self._sessions.values():
                if session.process:
                    try:
                        session.process.kill()
                    except ProcessLookupError:
                        pass
            self._sessions.clear()
            if self._browser:
                await self._browser.cleanup()
                self._browser = None
            logger.info("LocalSandbox destroyed")
            return True
        except Exception as e:
            logger.error(f"Failed to destroy LocalSandbox: {e}")
            return False

    @classmethod
    async def create(cls) -> 'LocalSandbox':
        sandbox = cls()
        logger.info(f"Created LocalSandbox: {sandbox.id}")
        return sandbox

    @classmethod
    async def get(cls, id: str) -> 'LocalSandbox':
        sandbox = cls()
        sandbox._id = id
        return sandbox

    def _resolve_path(self, path: str) -> str:
        if path.startswith("/home/ubuntu"):
            return path.replace("/home/ubuntu", SANDBOX_WORKDIR, 1)
        if path.startswith("/"):
            return path
        return os.path.join(SANDBOX_WORKDIR, path)
