import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FENCED_BASH = re.compile(r"^```bash\n(.*?)^```", re.MULTILINE | re.DOTALL)
FAKES = r"""
curl() { printf 'curl %s\n' "$*" >> "$FAKE_LOG"; printf '{"status":"ok"}'; }
claude() { printf 'claude depth=%s\n' "${BIPOLAR_DELEGATION_DEPTH-unset}" >> "$FAKE_LOG"; }
"""


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


def isolated_env(home, log, depth=None):
    env = {key: value for key, value in os.environ.items() if not key.startswith("BIPOLAR_")}
    env.update(HOME=home, FAKE_LOG=log, BIPOLAR_URL="http://bipolar.invalid:8000", BIPOLAR_API_KEY="test-key")
    if depth is not None:
        env["BIPOLAR_DELEGATION_DEPTH"] = depth
    return env


def run_block(block, depth=None):
    with tempfile.TemporaryDirectory() as home:
        log = os.path.join(home, "fake.log")
        Path(log).touch()
        completed = subprocess.run(
            [find_bash(), "-c", FAKES + block],
            env=isolated_env(home, log, depth),
            capture_output=True,
            text=True,
            timeout=60,
        )
        calls = Path(log).read_text(encoding="utf-8").splitlines()
    return completed, calls
