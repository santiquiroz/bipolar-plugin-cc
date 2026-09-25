import unittest

from harness import command, output, run

RUN = "bipolar-rescue-run"
TRICKY_TASK = "\n".join([
    "const a = `${x}`; echo $(whoami) $HOME",
    'He said "hi" and \\n stays; path C:\\tmp\\$USER',
    "don't stop at 'EOF'",
    "EOF",
])


def run_with_task(task):
    return run(command(RUN), stdin=task + "\n")


class RescueTaskPassingTest(unittest.TestCase):
    def test_task_reaches_the_child_without_shell_expansion(self):
        result = run_with_task(TRICKY_TASK)

        self.assertEqual(result.completed.returncode, 0, output(result.completed))
        self.assertTrue(result.claude_stdin.startswith(TRICKY_TASK + "\n"), result.claude_stdin)

    def test_task_travels_on_stdin_not_on_the_command_line(self):
        result = run_with_task(TRICKY_TASK)

        self.assertIn(TRICKY_TASK, result.claude_stdin)
        self.assertFalse(any("whoami" in arg for arg in result.claude_args))

    def test_prompt_ends_with_the_no_delegation_constraints(self):
        result = run_with_task("rename foo to bar in src/a.py")

        self.assertTrue(result.claude_stdin.rstrip().endswith("No delegues. No hagas commits."), result.claude_stdin)

    def test_child_git_never_waits_for_credentials(self):
        result = run_with_task("noop")

        self.assertIn("claude GIT_TERMINAL_PROMPT=0", result.calls)
        self.assertIn("claude GIT_SSH_COMMAND=ssh -o BatchMode=yes", result.calls)

    def test_an_empty_task_is_refused_before_launching_claude(self):
        result = run_with_task("  ")

        self.assertEqual(result.completed.returncode, 64, output(result.completed))
        self.assertEqual(result.claude_args, [])


if __name__ == "__main__":
    unittest.main()
