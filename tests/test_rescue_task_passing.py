import re
import unittest

from shell_blocks import block_containing, run_with_fakes

RESCUE = "agents/bipolar-rescue.md"
TASK_PLACEHOLDER = re.compile(r"<task text[^>\n]*>")
TRICKY_TASK = "\n".join([
    "const a = `${x}`; echo $(whoami) $HOME",
    'He said "hi" and \\n stays; path C:\\tmp\\$USER',
    "EOF",
])


def forwarding_block_with_task(task):
    block = block_containing(RESCUE, "--permission-mode")
    return TASK_PLACEHOLDER.sub(lambda _: task, block, count=1)


def delivered_prompt(run):
    if run.claude_stdin:
        return run.claude_stdin
    args = run.claude_args
    return args[args.index("-p") + 1]


class RescueTaskPassingTest(unittest.TestCase):
    def test_task_reaches_the_child_without_shell_expansion(self):
        run = run_with_fakes(forwarding_block_with_task(TRICKY_TASK))

        self.assertEqual(run.completed.returncode, 0, run.completed.stderr)
        self.assertTrue(delivered_prompt(run).startswith(TRICKY_TASK + "\n"), delivered_prompt(run))

    def test_task_travels_on_stdin_not_on_the_command_line(self):
        run = run_with_fakes(forwarding_block_with_task(TRICKY_TASK))

        self.assertIn(TRICKY_TASK, run.claude_stdin)
        self.assertFalse(any("whoami" in arg for arg in run.claude_args))

    def test_prompt_ends_with_the_no_delegation_constraints(self):
        run = run_with_fakes(forwarding_block_with_task("rename foo to bar in src/a.py"))

        self.assertIn("No delegues. No hagas commits.", delivered_prompt(run))

    def test_child_git_never_waits_for_credentials(self):
        run = run_with_fakes(forwarding_block_with_task("noop"))

        self.assertIn("claude GIT_TERMINAL_PROMPT=0", run.calls)
        self.assertIn("claude GIT_SSH_COMMAND=ssh -o BatchMode=yes", run.calls)


if __name__ == "__main__":
    unittest.main()
