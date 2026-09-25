import json
import re
import unittest

from shell_blocks import block_containing, run_with_fakes

RESCUE = "agents/bipolar-rescue.md"
BASH_TOOL_CEILING_S = 600
TIME_CAP = re.compile(r'\btimeout (\d+) "\$CLAUDE_BIN"')


def forwarding_block():
    return block_containing(RESCUE, "--permission-mode")


def run_child(block=None, **overrides):
    return run_with_fakes(block or forwarding_block(), **overrides)


def flag_value(args, flag):
    return args[args.index(flag) + 1]


def with_time_cap(block, seconds):
    return TIME_CAP.sub(f'timeout {seconds} "$CLAUDE_BIN"', block, count=1)


class RescueChildIsolationTest(unittest.TestCase):
    def test_child_runs_with_every_hook_disabled(self):
        run = run_child()

        self.assertEqual(json.loads(flag_value(run.claude_args, "--settings")), {"disableAllHooks": True})

    def test_child_loads_no_mcp_server_from_the_machine(self):
        run = run_child()

        self.assertIn("--strict-mcp-config", run.claude_args)
        self.assertNotIn("--mcp-config", run.claude_args)

    def test_child_turns_are_capped_like_the_broker(self):
        run = run_child()

        self.assertEqual(flag_value(run.claude_args, "--max-turns"), "50")

    def test_child_can_neither_delegate_nor_load_skills(self):
        run = run_child()

        disallowed = flag_value(run.claude_args, "--disallowedTools").split(",")
        self.assertTrue({"Task", "Agent", "Skill"} <= set(disallowed), disallowed)

    def test_child_time_cap_stays_under_the_bash_tool_ceiling(self):
        cap = TIME_CAP.search(forwarding_block())

        self.assertIsNotNone(cap, "the child claude must run under `timeout <s>`")
        self.assertLess(int(cap.group(1)), BASH_TOOL_CEILING_S)

    def test_child_over_the_time_cap_is_stopped_and_reported_as_partial(self):
        run = run_child(with_time_cap(forwarding_block(), 1), FAKE_CLAUDE_SLEEP="30")

        self.assertEqual(run.completed.returncode, 124, run.completed.stderr)
        self.assertIn("partial", run.completed.stdout.lower())

    def test_child_exit_code_passes_through(self):
        run = run_child(FAKE_CLAUDE_EXIT="3")

        self.assertEqual(run.completed.returncode, 3, run.completed.stderr)
        self.assertNotIn("partial", run.completed.stdout.lower())


if __name__ == "__main__":
    unittest.main()
