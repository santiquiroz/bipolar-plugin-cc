import json
import re
import unittest

from harness import BIN, StubServer, bash_blocks, block_containing, compact_json, output, run

DELEGATE = "commands/delegate.md"
RESCUE = "agents/bipolar-rescue.md"
SETUP = "commands/setup.md"
MARKDOWN = (DELEGATE, RESCUE, SETUP)
TASK_PLACEHOLDER = re.compile(r"<task text[^>\n]*>")
INLINE_LOGIC = ("curl", "claude -p", "BIPOLAR_URL", "BIPOLAR_API_KEY", "timeout ")
TRICKY_TASK = "\n".join([
    "don't touch `x` $(id) \"q\" and ${HOME}",
    "it's JS: const s = 'a' + `${b}`; path C:\\tmp\\$USER",
])


def every_block():
    return [(path, block) for path in MARKDOWN for block in bash_blocks(path)]


def invoked_script(block):
    return block.split()[0]


def with_task(block, task):
    return TASK_PLACEHOLDER.sub(lambda _: task, block, count=1)


class MarkdownInvokesScriptsTest(unittest.TestCase):
    def test_every_block_runs_a_script_of_the_plugin(self):
        for path, block in every_block():
            with self.subTest(path=path, block=block):
                self.assertTrue((BIN / invoked_script(block)).is_file(), block)

    def test_no_block_carries_logic_of_its_own(self):
        for path, block in every_block():
            for fragment in INLINE_LOGIC:
                with self.subTest(path=path, fragment=fragment):
                    self.assertNotIn(fragment, block)

    def test_every_script_is_used_by_the_markdown(self):
        used = {invoked_script(block) for _, block in every_block()}

        self.assertEqual(used, {script.name for script in BIN.iterdir()})


class MarkdownBlocksRunAsWrittenTest(unittest.TestCase):
    def test_delegate_submit_block_posts_the_task_intact(self):
        block = with_task(block_containing(DELEGATE, "bipolar-delegate-submit"), TRICKY_TASK)
        queued = (200, compact_json({"id": "job-1", "status": "queued"}))
        with StubServer({("POST", "/api/delegate/jobs"): queued}) as server:
            result = run(block, BIPOLAR_URL=server.url)

        self.assertEqual(result.completed.returncode, 0, output(result.completed))
        self.assertEqual(json.loads(server.requests[0].body)["task"], TRICKY_TASK)

    def test_delegate_wait_block_follows_the_job_by_its_id(self):
        block = block_containing(DELEGATE, "bipolar-delegate-wait").replace("<id>", "job-1")
        succeeded = (200, compact_json({"id": "job-1", "status": "succeeded"}))
        with StubServer({("GET", "/api/delegate/jobs/job-1"): succeeded}) as server:
            result = run(block, BIPOLAR_URL=server.url)

        self.assertEqual(result.completed.returncode, 0, output(result.completed))
        self.assertEqual(len(server.requests), 1)

    def test_rescue_run_block_hands_the_task_to_the_child(self):
        block = with_task(block_containing(RESCUE, "bipolar-rescue-run"), TRICKY_TASK)

        result = run(block)

        self.assertEqual(result.completed.returncode, 0, output(result.completed))
        self.assertTrue(result.claude_stdin.startswith(TRICKY_TASK + "\n"), result.claude_stdin)


if __name__ == "__main__":
    unittest.main()
