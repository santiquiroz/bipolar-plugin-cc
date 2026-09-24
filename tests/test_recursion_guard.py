import unittest

from shell_blocks import bash_blocks, block_containing, run_block

DELEGATE = "commands/delegate.md"
RESCUE = "agents/bipolar-rescue.md"


def curl_calls(calls):
    return [call for call in calls if call.startswith("curl ")]


class DelegateRecursionGuardTest(unittest.TestCase):
    def test_config_step_refuses_inside_a_delegated_child_before_any_request(self):
        completed, calls = run_block(bash_blocks(DELEGATE)[0], depth="1")

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("recursion", completed.stdout.lower())
        self.assertEqual(curl_calls(calls), [])

    def test_config_step_reaches_the_server_at_top_level(self):
        completed, calls = run_block(bash_blocks(DELEGATE)[0])

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(curl_calls(calls)), 2)

    def test_submit_forwards_the_inherited_depth(self):
        _, calls = run_block(block_containing(DELEGATE, "-X POST"), depth="1")

        self.assertIn("X-Bipolar-Depth: 1", curl_calls(calls)[0])

    def test_submit_sends_depth_zero_at_top_level(self):
        _, calls = run_block(block_containing(DELEGATE, "-X POST"))

        self.assertIn("X-Bipolar-Depth: 0", curl_calls(calls)[0])


class RescueRecursionGuardTest(unittest.TestCase):
    def test_health_check_refuses_inside_a_delegated_child_before_any_request(self):
        completed, calls = run_block(bash_blocks(RESCUE)[0], depth="1")

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("recursion", completed.stdout.lower())
        self.assertEqual(curl_calls(calls), [])

    def test_child_claude_is_marked_as_delegated(self):
        _, calls = run_block(block_containing(RESCUE, "--permission-mode"))

        self.assertIn("claude depth=1", calls)


if __name__ == "__main__":
    unittest.main()
