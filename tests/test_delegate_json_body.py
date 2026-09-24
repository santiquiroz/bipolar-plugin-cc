import json
import os
import re
import unittest

from shell_blocks import block_containing, run_with_fakes

DELEGATE = "commands/delegate.md"
TASK_PLACEHOLDER = re.compile(r"<task text[^>\n]*>")
WORKSPACE = "C:/personal/some repo"
TRICKY_TASK = "\n".join([
    "don't touch `x` $(id) \"q\" and ${HOME}",
    "it's JS: const s = 'a' + `${b}`; path C:\\tmp\\$USER \\n stays",
    "line3 ünïcode",
])
BODY_ARGUMENT = re.compile(r"--data-binary @(\S+)")


def submit_block(task=TRICKY_TASK, **options):
    block = block_containing(DELEGATE, "-X POST")
    block = TASK_PLACEHOLDER.sub(lambda _: task, block, count=1)
    for name, value in {"WORKSPACE": f"'{WORKSPACE}'", **options}.items():
        block = re.sub(rf"(?<![\w$]){name}=\S*", f"{name}={value}", block, count=1)
    return block


def posted_body(run):
    return json.loads(run.curl_body)


def posted_body_path(run):
    call = next(call for call in run.calls if call.startswith("curl "))
    return BODY_ARGUMENT.search(call).group(1)


class DelegateJsonBodyTest(unittest.TestCase):
    def test_task_is_posted_byte_for_byte(self):
        run = run_with_fakes(submit_block())

        self.assertEqual(run.completed.returncode, 0, run.completed.stderr)
        self.assertEqual(posted_body(run)["task"], TRICKY_TASK)

    def test_body_is_sent_from_a_file_not_inline(self):
        run = run_with_fakes(submit_block())

        self.assertIsNotNone(posted_body_path(run))
        self.assertNotIn("don't", "\n".join(run.calls))

    def test_default_body_carries_only_task_workspace_and_mode(self):
        run = run_with_fakes(submit_block())

        self.assertEqual(posted_body(run), {"task": TRICKY_TASK, "workspace": WORKSPACE, "mode": "task"})

    def test_flags_add_their_optional_fields(self):
        run = run_with_fakes(submit_block(MODE="text", AGENT="codex", TIER="complex", DRY_RUN="1"))

        self.assertEqual(posted_body(run), {
            "task": TRICKY_TASK,
            "workspace": WORKSPACE,
            "mode": "text",
            "agent_id": "codex",
            "tier_hint": "complex",
            "dry_run": True,
        })

    def test_python_builds_the_same_body_when_node_is_missing(self):
        run = run_with_fakes("node() { return 127; }\n" + submit_block(AGENT="claude"))

        self.assertEqual(run.completed.returncode, 0, run.completed.stderr)
        self.assertEqual(posted_body(run), {
            "task": TRICKY_TASK, "workspace": WORKSPACE, "mode": "task", "agent_id": "claude",
        })

    def test_timeout_flag_adds_an_integer_timeout_s(self):
        run = run_with_fakes(submit_block(TIMEOUT_S="1800"))

        self.assertEqual(posted_body(run)["timeout_s"], 1800)

    def test_python_adds_the_same_integer_timeout_s(self):
        run = run_with_fakes("node() { return 127; }\n" + submit_block(TIMEOUT_S="1800"))

        self.assertEqual(run.completed.returncode, 0, run.completed.stderr)
        self.assertEqual(posted_body(run)["timeout_s"], 1800)

    def test_temporary_files_are_removed_after_posting(self):
        run = run_with_fakes(submit_block())

        self.assertFalse(os.path.exists(posted_body_path(run)))


if __name__ == "__main__":
    unittest.main()
