import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import threading
from collections import namedtuple
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BIN = REPO / "bin"
LIB = REPO / "lib"
FENCED_BASH = re.compile(r"^```bash\n(.*?)^```", re.MULTILINE | re.DOTALL)
UNREACHABLE_URL = "http://bipolar.invalid:8000"
PROXY_VARIABLES = ("http_proxy", "https_proxy", "all_proxy", "no_proxy")
RUN_TIMEOUT_S = 120
FAKE_CLAUDE = r"""#!/usr/bin/env bash
printf 'claude depth=%s\n' "${BIPOLAR_DELEGATION_DEPTH-unset}" >> "$FAKE_LOG"
printf 'claude GIT_TERMINAL_PROMPT=%s\n' "${GIT_TERMINAL_PROMPT-unset}" >> "$FAKE_LOG"
printf 'claude GIT_SSH_COMMAND=%s\n' "${GIT_SSH_COMMAND-unset}" >> "$FAKE_LOG"
printf 'claude ANTHROPIC_BASE_URL=%s\n' "${ANTHROPIC_BASE_URL-unset}" >> "$FAKE_LOG"
printf 'claude ANTHROPIC_API_KEY=%s\n' "${ANTHROPIC_API_KEY-unset}" >> "$FAKE_LOG"
printf '%s\0' "$@" > "$FAKE_CLAUDE_ARGS"
cat > "$FAKE_CLAUDE_STDIN"
[ -n "${FAKE_CLAUDE_SLEEP-}" ] && exec sleep "$FAKE_CLAUDE_SLEEP"
exit "${FAKE_CLAUDE_EXIT:-0}"
"""
# Logs the command line, then runs the real curl against the test's stub server
LOGGING_CURL = r"""#!/usr/bin/env bash
printf 'curl %s\n' "$*" >> "$FAKE_LOG"
exec "$REAL_CURL" "$@"
"""
# Git Bash's launcher puts /mingw64/bin and /usr/bin first, so the fakes are prepended from inside the shell
PATH_PRELUDE = r"""
PATH="$TEST_PATH:$PATH"
"""
# Git for Windows loses a multi-line -c script's last command when bash execs it in place of itself
NO_EXEC_EPILOGUE = "\nexit $?\n"
Run = namedtuple("Run", "completed calls claude_args claude_stdin")
Request = namedtuple("Request", "method path api_key headers body")


def compact_json(value):
    # Starlette's JSONResponse serializes without spaces
    return json.dumps(value, separators=(",", ":"))


def command(*words):
    return " ".join(shlex.quote(str(word)) for word in words)


def bash_blocks(relative_path):
    text = (REPO / relative_path).read_text(encoding="utf-8")
    return FENCED_BASH.findall(text)


def block_containing(relative_path, marker):
    return next(block for block in bash_blocks(relative_path) if marker in block)


def run(script, stdin="", cwd=None, prelude="", plugin_bin=BIN, depth=None, **overrides):
    with tempfile.TemporaryDirectory() as home:
        env = _isolated_env(home, plugin_bin, depth)
        env.update(overrides)
        completed = run_bash(PATH_PRELUDE + prelude + script + NO_EXEC_EPILOGUE, env, stdin, cwd)
        return Run(
            completed=completed,
            calls=_read_text(env["FAKE_LOG"]).splitlines(),
            claude_args=[arg for arg in _read_text(env["FAKE_CLAUDE_ARGS"]).split("\0") if arg],
            claude_stdin=_read_text(env["FAKE_CLAUDE_STDIN"]),
        )


def _isolated_env(home, plugin_bin, depth):
    removed = ("BIPOLAR_", "GIT_", "MSYS2_ARG_CONV")
    env = {key: value for key, value in os.environ.items() if not key.startswith(removed)}
    env = {key: value for key, value in env.items() if key.lower() not in PROXY_VARIABLES}
    fake_paths = {name: os.path.join(home, name) for name in ("fake.log", "claude.args", "claude.stdin")}
    for path in fake_paths.values():
        Path(path).touch()
    env.update(
        HOME=home,
        FAKE_LOG=fake_paths["fake.log"],
        FAKE_CLAUDE_ARGS=fake_paths["claude.args"],
        FAKE_CLAUDE_STDIN=fake_paths["claude.stdin"],
        BIPOLAR_URL=UNREACHABLE_URL,
        BIPOLAR_API_KEY="test-key",
        REAL_CURL=real_curl(),
        TEST_PATH=":".join(shell_path(folder) for folder in (
            _install(home, "fake-claude-bin", "claude", FAKE_CLAUDE),
            _install(home, "fake-tools-bin", "curl", LOGGING_CURL),
            str(plugin_bin),
        )),
    )
    if depth is not None:
        env["BIPOLAR_DELEGATION_DEPTH"] = depth
    return env


def _install(home, folder, name, text):
    directory = Path(home) / folder
    directory.mkdir()
    _write_executable(directory / name, text)
    return str(directory)


def _write_executable(path, text):
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def shell_path(native):
    if os.name != "nt":
        return native
    drive, rest = os.path.splitdrive(Path(native).as_posix())
    return f"/{drive[0].lower()}{rest}"


def real_curl():
    bash = Path(find_bash())
    bundled = bash.parents[1] / "mingw64" / "bin" / "curl.exe"
    return shell_path(str(bundled)) if bundled.exists() else shutil.which("curl")


def curl_calls(run_result):
    return [call for call in run_result.calls if call.startswith("curl ")]


def claude_calls(run_result):
    return [call for call in run_result.calls if call.startswith("claude ")]


def output(completed):
    return completed.stdout + completed.stderr


@contextmanager
def patched_plugin_bin(script, **assignments):
    with tempfile.TemporaryDirectory() as root:
        shutil.copytree(BIN, Path(root) / "bin")
        shutil.copytree(LIB, Path(root) / "lib")
        target = Path(root) / "bin" / script
        _write_executable(target, _assign(target.read_text(encoding="utf-8"), assignments))
        yield Path(root) / "bin"


def _assign(text, assignments):
    for name, value in assignments.items():
        text, count = re.subn(rf"(?<![\w$]){name}=\S*", f"{name}={value}", text, count=1)
        if count != 1:
            raise AssertionError(f"no {name}= assignment to patch")
    return text


def script_assignment(script, name):
    text = (BIN / script).read_text(encoding="utf-8")
    return int(re.search(rf"(?<![\w$]){name}=(\d+)", text).group(1))


def find_bash():
    override = os.environ.get("BIPOLAR_TEST_BASH")
    if override:
        return override
    if os.name == "nt":
        return _git_for_windows_bash() or shutil.which("bash")
    return shutil.which("bash")


def _git_for_windows_bash():
    # A bare "bash" on Windows may resolve to WSL's bash.exe, which does not inherit this environment
    git = shutil.which("git")
    if not git:
        return None
    for folder in Path(git).resolve().parents:
        candidate = folder / "bin" / "bash.exe"
        if candidate.exists():
            return str(candidate)
    return None


def run_bash(script, env, stdin="", cwd=None):
    # Bytes both ways: text mode would turn the task's \n into \r\n on Windows
    process = subprocess.Popen(
        [find_bash(), "-c", script],
        env=env,
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=os.name != "nt",
    )
    try:
        stdout, stderr = process.communicate(stdin.encode("utf-8"), timeout=RUN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        _kill_tree(process.pid)
        process.communicate()
        raise
    return subprocess.CompletedProcess(process.args, process.returncode, _decode(stdout), _decode(stderr))


def _kill_tree(pid):
    # Git for Windows' bin/bash.exe is a launcher: killing only it leaves the real bash holding the pipes
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
    else:
        os.killpg(pid, signal.SIGKILL)


def _decode(data):
    return data.decode("utf-8").replace("\r\n", "\n")


def _read_text(path):
    return Path(path).read_bytes().decode("utf-8")


class StubServer:
    def __init__(self, routes=None, headers=None):
        self.routes = {key: list(value) if isinstance(value, list) else [value] for key, value in (routes or {}).items()}
        self.headers = headers or {}
        self.requests = []
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())

    def _next_response(self, key):
        responses = self.routes.get(key)
        if not responses:
            return 404, '{"detail":"Not Found"}'
        return responses.pop(0) if len(responses) > 1 else responses[0]

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self._answer()

            def do_POST(self):
                self._answer()

            def do_DELETE(self):
                self._answer()

            def _answer(self):
                length = int(self.headers.get("content-length") or 0)
                body = self.rfile.read(length).decode("utf-8")
                headers = {name.lower(): value for name, value in self.headers.items()}
                server.requests.append(Request(self.command, self.path, headers.get("x-api-key"), headers, body))
                code, payload = server._next_response((self.command, self.path))
                self._send(code, payload.encode("utf-8"), server.headers.get((self.command, self.path), {}))

            def _send(self, code, payload, extra_headers):
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                for name, value in extra_headers.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        return Handler

    @property
    def url(self):
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def __enter__(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
