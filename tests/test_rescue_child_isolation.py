import json
import unittest

from harness import command, output, patched_plugin_bin, run, script_assignment

RUN = "bipolar-rescue-run"
BASH_TOOL_CEILING_S = 600


def run_child(plugin_bin=None, **overrides):
    extra = {"plugin_bin": plugin_bin} if plugin_bin else {}
    return run(command(RUN), stdin="task\n", **extra, **overrides)


def flag_value(args, flag):
    return args[args.index(flag) + 1]


class RescueChildIsolationTest(unittest.TestCase):
    def test_child_runs_with_every_hook_disabled(self):
        result = run_child()

        self.assertEqual(json.loads(flag_value(result.claude_args, "--settings")), {"disableAllHooks": True})

    def test_child_loads_no_mcp_server_from_the_machine(self):
        result = run_child()

        self.assertIn("--strict-mcp-config", result.claude_args)
        self.assertNotIn("--mcp-config", result.claude_args)

    def test_child_turns_are_capped_like_the_broker(self):
        result = run_child()

        self.assertEqual(flag_value(result.claude_args, "--max-turns"), "50")

    def test_child_can_neither_delegate_nor_load_skills(self):
        result = run_child()

        disallowed = flag_value(result.claude_args, "--disallowedTools").split(",")
        self.assertTrue({"Task", "Agent", "Skill"} <= set(disallowed), disallowed)

    def test_child_time_cap_stays_under_the_bash_tool_ceiling(self):
        self.assertLess(script_assignment(RUN, "TIME_CAP_S"), BASH_TOOL_CEILING_S)

    def test_child_over_the_time_cap_is_stopped_and_reported_as_partial(self):
        with patched_plugin_bin(RUN, TIME_CAP_S="1") as plugin_bin:
            result = run_child(plugin_bin, FAKE_CLAUDE_SLEEP="30")

        self.assertEqual(result.completed.returncode, 124, output(result.completed))
        self.assertIn("partial", result.completed.stdout.lower())

    def test_child_exit_code_passes_through(self):
        result = run_child(FAKE_CLAUDE_EXIT="3")

        self.assertEqual(result.completed.returncode, 3, output(result.completed))
        self.assertNotIn("partial", result.completed.stdout.lower())


if __name__ == "__main__":
    unittest.main()
