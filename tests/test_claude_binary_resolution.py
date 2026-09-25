import unittest

from harness import StubServer, claude_calls, command, output, run
from test_health_checks import setup_routes, write_config

NOT_FOUND_EXIT = 79
# Drops every PATH entry that holds a claude, the test's fake included, so no real CLI can run
WITHOUT_CLAUDE_ON_PATH = r"""
kept= IFS_BEFORE=$IFS IFS=:
for dir in $PATH; do
  [ -e "$dir/claude" ] || [ -e "$dir/claude.exe" ] || kept="$kept${kept:+:}$dir"
done
IFS=$IFS_BEFORE PATH=$kept
"""
FAKE_AT_LOCAL_BIN = r"""
mkdir -p "$HOME/.local/bin" && cp "$(command -v claude)" "$HOME/.local/bin/claude.exe"
"""


def rescue_run(prelude=""):
    return run(command("bipolar-rescue-run"), stdin="task\n", prelude=prelude)


def setup_verify(prelude):
    with StubServer(setup_routes()) as server:
        return run(command("bipolar-setup-verify"), prelude=write_config() + prelude, BIPOLAR_URL=server.url)


class RescueClaudeBinaryTest(unittest.TestCase):
    def test_child_runs_the_claude_found_on_path(self):
        result = rescue_run()

        self.assertEqual(result.completed.returncode, 0, output(result.completed))
        self.assertIn("claude depth=1", result.calls)

    def test_child_falls_back_to_the_installer_location_when_path_misses_it(self):
        result = rescue_run(FAKE_AT_LOCAL_BIN + WITHOUT_CLAUDE_ON_PATH)

        self.assertEqual(result.completed.returncode, 0, output(result.completed))
        self.assertIn("claude depth=1", result.calls)

    def test_missing_claude_is_reported_before_anything_runs(self):
        result = rescue_run(WITHOUT_CLAUDE_ON_PATH)

        self.assertEqual(result.completed.returncode, NOT_FOUND_EXIT, output(result.completed))
        self.assertIn("claude CLI not found", result.completed.stdout)
        self.assertEqual(claude_calls(result), [])


class SetupClaudeBinaryTest(unittest.TestCase):
    def test_setup_reports_the_installer_location_when_path_misses_it(self):
        result = setup_verify(FAKE_AT_LOCAL_BIN + WITHOUT_CLAUDE_ON_PATH)

        self.assertRegex(result.completed.stdout, r"claude CLI: \S*/\.local/bin/claude\.exe")

    def test_setup_reports_a_missing_claude(self):
        result = setup_verify(WITHOUT_CLAUDE_ON_PATH)

        self.assertIn("claude CLI: NOT FOUND", result.completed.stdout)


if __name__ == "__main__":
    unittest.main()
