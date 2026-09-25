import os
import re
import shutil
import signal
import subprocess
import tempfile
from collections import namedtuple
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FENCED_BASH = re.compile(r"^```bash\n(.*?)^```", re.MULTILINE | re.DOTALL)
FAKES = r"""
curl() {
  printf 'curl %s\n' "$*" >> "$FAKE_LOG"
  for arg in "$@"; do case "$arg" in @*) cat "${arg#@}" > "$FAKE_CURL_BODY";; esac; done
  case "$*" in *'%{http_code}'*) printf '200'; return;; esac
  printf '{"status":"ok"}'
}
"""
# An executable on PATH, not a function: a wrapper such as `timeout` must reach the fake too
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
FakeRun = namedtuple("FakeRun", "completed calls claude_args claude_stdin curl_body")
PROXY_VARIABLES = ("http_proxy", "https_proxy", "all_proxy", "no_proxy")
BLOCK_TIMEOUT_S = 120


def bash_blocks(relative_path):
    text = (REPO / relative_path).read_text(encoding="utf-8")
    return FENCED_BASH.findall(text)


def block_containing(relative_path, marker):
    return next(block for block in bash_blocks(relative_path) if marker in block)


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


def isolated_env(home, depth=None):
    env = {key: value for key, value in os.environ.items() if not key.startswith(("BIPOLAR_", "GIT_"))}
    env.update(
        HOME=home,
        FAKE_LOG=os.path.join(home, "fake.log"),
        FAKE_CLAUDE_ARGS=os.path.join(home, "claude.args"),
        FAKE_CLAUDE_STDIN=os.path.join(home, "claude.stdin"),
        FAKE_CURL_BODY=os.path.join(home, "curl.body"),
        BIPOLAR_URL="http://bipolar.invalid:8000",
        BIPOLAR_API_KEY="test-key",
    )
    if depth is not None:
        env["BIPOLAR_DELEGATION_DEPTH"] = depth
    return env


def run_block(block, depth=None):
    run = run_with_fakes(block, depth)
    return run.completed, run.calls


def run_with_fakes(block, depth=None, **overrides):
    with tempfile.TemporaryDirectory() as home:
        env = {**isolated_env(home, depth), **overrides}
        env["PATH"] = _install_fake_claude(home) + os.pathsep + env.get("PATH", "")
        for name in ("FAKE_LOG", "FAKE_CLAUDE_ARGS", "FAKE_CLAUDE_STDIN", "FAKE_CURL_BODY"):
            Path(env[name]).touch()
        completed = run_bash(FAKES + block, env)
        return FakeRun(
            completed=completed,
            calls=_read_text(env["FAKE_LOG"]).splitlines(),
            claude_args=[arg for arg in _read_text(env["FAKE_CLAUDE_ARGS"]).split("\0") if arg],
            claude_stdin=_read_text(env["FAKE_CLAUDE_STDIN"]),
            curl_body=_read_text(env["FAKE_CURL_BODY"]),
        )


def _install_fake_claude(home):
    fake_bin = Path(home) / "fake-bin"
    fake_bin.mkdir()
    script = fake_bin / "claude"
    script.write_text(FAKE_CLAUDE, encoding="utf-8", newline="\n")
    script.chmod(0o755)
    return str(fake_bin)


def run_with_real_curl(block, **overrides):
    with tempfile.TemporaryDirectory() as home:
        env = {key: value for key, value in isolated_env(home).items() if key.lower() not in PROXY_VARIABLES}
        env.update(overrides)
        return run_bash(block, env)


def run_bash(script, env):
    process = subprocess.Popen(
        [find_bash(), "-c", script],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=os.name != "nt",
    )
    try:
        stdout, stderr = process.communicate(timeout=BLOCK_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        _kill_tree(process.pid)
        process.communicate()
        raise
    return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)


def _kill_tree(pid):
    # Git for Windows' bin/bash.exe is a launcher: killing only it leaves the real bash holding the pipes
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
    else:
        os.killpg(pid, signal.SIGKILL)


def _read_text(path):
    return Path(path).read_bytes().decode("utf-8")
