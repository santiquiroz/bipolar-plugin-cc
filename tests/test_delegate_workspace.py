import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from shell_blocks import block_containing, run_with_fakes

DELEGATE = "commands/delegate.md"
TASK_PLACEHOLDER = re.compile(r"<task text[^>\n]*>")
BROKER_WORKSPACE_ERRORS = (
    "workspace_allowlist_empty",
    "workspace_required",
    "workspace_not_absolute",
    "workspace_missing",
    "workspace_not_dir",
    "workspace_forbidden",
    "workspace_not_allowed",
)
# MSYS rewrites /c/... arguments of native programs such as node, so the shell's own value is checked too
SHOW_WORKSPACE = r"""
printf 'computed workspace=%s\n' "$WORKSPACE"
"""
COMPUTED_WORKSPACE = re.compile(r"computed workspace=(.*)$", re.MULTILINE)
NO_PWD_W = r"""
pwd() { [ "$1" = -W ] && return 2; builtin pwd "$@"; }
"""
# cygpath keeps working for the temporary body file; only converting the workspace fails
NO_NATIVE_PATH_TOOLS = NO_PWD_W + r"""
if command -v cygpath >/dev/null; then
  cygpath() { [ "$2" = "$PWD" ] && return 1; command cygpath "$@"; }
fi
"""


def submit_block_without_workspace_flag():
    block = block_containing(DELEGATE, "-X POST")
    return TASK_PLACEHOLDER.sub(lambda _: "task", block, count=1)


def run_submit_from(directory, prelude=""):
    change_directory = f"cd '{Path(directory).as_posix()}' || exit 1\n"
    return run_with_fakes(change_directory + prelude + submit_block_without_workspace_flag() + SHOW_WORKSPACE)


def computed_workspace(run):
    return COMPUTED_WORKSPACE.search(run.completed.stdout).group(1)


def posted_workspace(run):
    return json.loads(run.curl_body)["workspace"]


class DelegateWorkspaceDefaultTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="ws dir ")
        self.addCleanup(os.rmdir, self.directory)

    def test_default_workspace_is_the_current_directory(self):
        run = run_submit_from(self.directory)

        self.assertEqual(run.completed.returncode, 0, run.completed.stderr)
        self.assertTrue(os.path.samefile(posted_workspace(run), self.directory))

    def test_default_workspace_is_absolute_for_the_servers_python(self):
        run = run_submit_from(self.directory)

        self.assertTrue(Path(posted_workspace(run)).is_absolute(), posted_workspace(run))

    @unittest.skipUnless(os.name == "nt", "Git Bash path forms only exist on Windows")
    def test_default_workspace_uses_the_drive_letter_form_on_windows(self):
        run = run_submit_from(self.directory)

        self.assertRegex(computed_workspace(run), r"^[A-Za-z]:/")

    @unittest.skipUnless(os.name == "nt", "cygpath only exists on Windows")
    def test_default_workspace_falls_back_to_cygpath_without_pwd_w(self):
        run = run_submit_from(self.directory, prelude=NO_PWD_W)

        self.assertEqual(run.completed.returncode, 0, run.completed.stderr)
        self.assertRegex(computed_workspace(run), r"^[A-Za-z]:/")
        self.assertTrue(os.path.samefile(posted_workspace(run), self.directory))

    def test_default_workspace_falls_back_to_pwd_without_native_path_tools(self):
        run = run_submit_from(self.directory, prelude=NO_NATIVE_PATH_TOOLS)

        self.assertEqual(run.completed.returncode, 0, run.completed.stderr)
        self.assertTrue(computed_workspace(run).startswith("/"), computed_workspace(run))
        self.assertTrue(os.path.samefile(posted_workspace(run), self.directory))


class DelegateWorkspaceErrorTableTest(unittest.TestCase):
    def test_every_workspace_error_of_the_broker_has_an_action(self):
        lines = (Path(__file__).resolve().parents[1] / DELEGATE).read_text(encoding="utf-8").splitlines()
        table = [line for line in lines if line.startswith("- 400 ")]

        for code in BROKER_WORKSPACE_ERRORS:
            with self.subTest(code=code):
                self.assertTrue(any(f"`{code}`" in line for line in table), code)


if __name__ == "__main__":
    unittest.main()
