import json
import os
import tempfile
import unittest
from pathlib import Path

from harness import REPO, StubServer, command, compact_json, output, run

DELEGATE = "commands/delegate.md"
JOBS_PATH = "/api/delegate/jobs"
BROKER_WORKSPACE_ERRORS = (
    "workspace_allowlist_empty",
    "workspace_required",
    "workspace_not_absolute",
    "workspace_missing",
    "workspace_not_dir",
    "workspace_forbidden",
    "workspace_not_allowed",
)
# MSYS rewrites /c/... arguments of native programs such as node; this shows the shell's own value
NO_ARGUMENT_CONVERSION = {"MSYS2_ARG_CONV_EXCL": "*"}
NO_PWD_W = r"""
pwd() { [ "$1" = -W ] && return 2; builtin pwd "$@"; }
export -f pwd
"""
# cygpath keeps working for the temporary body file; only converting the workspace fails
NO_NATIVE_PATH_TOOLS = NO_PWD_W + r"""
if command -v cygpath >/dev/null; then
  cygpath() { [ "$2" = "$PWD" ] && return 1; command cygpath "$@"; }
  export -f cygpath
fi
"""


def posted_workspace(directory, prelude="", **overrides):
    with StubServer({("POST", JOBS_PATH): (200, compact_json({"id": "job-1", "status": "queued"}))}) as server:
        result = run(command("bipolar-delegate-submit"), stdin="task\n", cwd=directory, prelude=prelude,
                     BIPOLAR_URL=server.url, **overrides)
    if result.completed.returncode != 0:
        raise AssertionError(output(result.completed))
    return json.loads(server.requests[0].body)["workspace"]


class DelegateWorkspaceDefaultTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="ws dir ")
        self.addCleanup(os.rmdir, self.directory)

    def test_default_workspace_is_the_current_directory(self):
        self.assertTrue(os.path.samefile(posted_workspace(self.directory), self.directory))

    def test_default_workspace_is_absolute_for_the_servers_python(self):
        workspace = posted_workspace(self.directory)

        self.assertTrue(Path(workspace).is_absolute(), workspace)

    @unittest.skipUnless(os.name == "nt", "Git Bash path forms only exist on Windows")
    def test_default_workspace_uses_the_drive_letter_form_on_windows(self):
        workspace = posted_workspace(self.directory, **NO_ARGUMENT_CONVERSION)

        self.assertRegex(workspace, r"^[A-Za-z]:/")

    @unittest.skipUnless(os.name == "nt", "cygpath only exists on Windows")
    def test_default_workspace_falls_back_to_cygpath_without_pwd_w(self):
        workspace = posted_workspace(self.directory, prelude=NO_PWD_W, **NO_ARGUMENT_CONVERSION)

        self.assertRegex(workspace, r"^[A-Za-z]:/")
        self.assertTrue(os.path.samefile(workspace, self.directory))

    def test_default_workspace_falls_back_to_pwd_without_native_path_tools(self):
        workspace = posted_workspace(self.directory, prelude=NO_NATIVE_PATH_TOOLS)

        self.assertTrue(os.path.samefile(workspace, self.directory))

    @unittest.skipUnless(os.name == "nt", "Git Bash path forms only exist on Windows")
    def test_the_last_fallback_is_git_bash_form_on_windows(self):
        workspace = posted_workspace(self.directory, prelude=NO_NATIVE_PATH_TOOLS, **NO_ARGUMENT_CONVERSION)

        self.assertTrue(workspace.startswith("/"), workspace)


class DelegateWorkspaceErrorTableTest(unittest.TestCase):
    def test_every_workspace_error_of_the_broker_has_an_action(self):
        lines = (REPO / DELEGATE).read_text(encoding="utf-8").splitlines()
        table = [line for line in lines if line.startswith("- 400 ")]

        for code in BROKER_WORKSPACE_ERRORS:
            with self.subTest(code=code):
                self.assertTrue(any(f"`{code}`" in line for line in table), code)


if __name__ == "__main__":
    unittest.main()
