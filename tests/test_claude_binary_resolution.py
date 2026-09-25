import unittest

from shell_blocks import block_containing, run_with_fakes

RESCUE = "agents/bipolar-rescue.md"
SETUP = "commands/setup.md"
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


def forwarding_block():
    return block_containing(RESCUE, "--permission-mode")


def setup_verify_block():
    return block_containing(SETUP, "/api/llamacpp/status")


def claude_calls(run):
    return [call for call in run.calls if call.startswith("claude ")]


class RescueClaudeBinaryTest(unittest.TestCase):
    def test_child_runs_the_claude_found_on_path(self):
        run = run_with_fakes(forwarding_block())

        self.assertEqual(run.completed.returncode, 0, run.completed.stderr)
        self.assertIn("claude depth=1", run.calls)

    def test_child_falls_back_to_the_installer_location_when_path_misses_it(self):
        run = run_with_fakes(FAKE_AT_LOCAL_BIN + WITHOUT_CLAUDE_ON_PATH + forwarding_block())

        self.assertEqual(run.completed.returncode, 0, run.completed.stdout + run.completed.stderr)
        self.assertIn("claude depth=1", run.calls)

    def test_missing_claude_is_reported_before_anything_runs(self):
        run = run_with_fakes(WITHOUT_CLAUDE_ON_PATH + forwarding_block())

        self.assertEqual(run.completed.returncode, NOT_FOUND_EXIT, run.completed.stdout + run.completed.stderr)
        self.assertIn("claude CLI not found", run.completed.stdout)
        self.assertEqual(claude_calls(run), [])


class SetupClaudeBinaryTest(unittest.TestCase):
    def test_setup_reports_the_installer_location_when_path_misses_it(self):
        run = run_with_fakes(FAKE_AT_LOCAL_BIN + WITHOUT_CLAUDE_ON_PATH + setup_verify_block())

        self.assertRegex(run.completed.stdout, r"claude CLI: \S*/\.local/bin/claude\.exe")

    def test_setup_reports_a_missing_claude(self):
        run = run_with_fakes(WITHOUT_CLAUDE_ON_PATH + setup_verify_block())

        self.assertIn("claude CLI: NOT FOUND", run.completed.stdout)


if __name__ == "__main__":
    unittest.main()
