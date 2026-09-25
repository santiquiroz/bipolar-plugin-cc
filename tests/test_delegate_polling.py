import json
import unittest

from harness import BIN, StubServer, UNREACHABLE_URL, command, compact_json, output, patched_plugin_bin, run, script_assignment

WAIT = "bipolar-delegate-wait"
JOB_ID = "job-7f3a"
JOB_PATH = f"/api/delegate/jobs/{JOB_ID}"
BASH_TOOL_CEILING_S = 600
REQUEST_CAP_S = 20


def job(status, **fields):
    return 200, compact_json({"id": JOB_ID, "status": status, "output_tail": "", "error": "", **fields})


NOT_FOUND = (404, compact_json({"detail": "Job no encontrado"}))
SERVER_ERROR = (502, "<html>Bad Gateway</html>")


def wait_for_job(url, **assignments):
    with patched_plugin_bin(WAIT, **{"POLL_S": "0", **assignments}) as plugin_bin:
        return run(command(WAIT, JOB_ID), plugin_bin=plugin_bin, BIPOLAR_URL=url).completed


def poll(responses, **assignments):
    with StubServer({("GET", JOB_PATH): responses}) as server:
        completed = wait_for_job(server.url, **assignments)
    return completed, server.requests


def final_status(completed):
    return json.loads(completed.stdout.strip().splitlines()[-1])["status"]


class DelegatePollingTest(unittest.TestCase):
    def test_polls_while_running_until_the_job_succeeds(self):
        completed, requests = poll([job("running")] * 3 + [job("succeeded", output_tail="done")])

        self.assertEqual(completed.returncode, 0, output(completed))
        self.assertEqual(final_status(completed), "succeeded")
        self.assertEqual(len(requests), 4)
        self.assertEqual((requests[0].method, requests[0].path, requests[0].api_key), ("GET", JOB_PATH, "test-key"))

    def test_keeps_polling_after_a_failed_status_read(self):
        completed, requests = poll([SERVER_ERROR, (200, ""), job("queued"), job("failed", error="max_attempts")])

        self.assertEqual(completed.returncode, 0, output(completed))
        self.assertEqual(final_status(completed), "failed")
        self.assertEqual(len(requests), 4)

    def test_gives_up_after_three_failed_status_reads_in_a_row(self):
        completed, requests = poll([SERVER_ERROR])

        self.assertEqual(completed.returncode, 74, output(completed))
        self.assertEqual(len(requests), 3)
        self.assertIn("502", completed.stdout)

    def test_gives_up_when_the_server_is_unreachable(self):
        completed = wait_for_job(UNREACHABLE_URL)

        self.assertEqual(completed.returncode, 74, output(completed))

    def test_reports_a_missing_job_as_lost_without_retrying(self):
        completed, requests = poll([NOT_FOUND])

        self.assertEqual(completed.returncode, 76, output(completed))
        self.assertEqual(len(requests), 1)
        self.assertIn("restarted", completed.stdout)

    def test_ends_the_segment_with_the_job_still_running(self):
        completed, requests = poll([job("running")], SEGMENT_S="0")

        self.assertEqual(completed.returncode, 75, output(completed))
        self.assertEqual(len(requests), 1)
        self.assertIn(f"run bipolar-delegate-wait {JOB_ID} again", completed.stdout)

    def test_segment_fits_inside_the_bash_tool_ceiling(self):
        segment = script_assignment(WAIT, "SEGMENT_S")
        poll_interval = script_assignment(WAIT, "POLL_S")

        self.assertLessEqual(segment + poll_interval + REQUEST_CAP_S, BASH_TOOL_CEILING_S)

    def test_request_cap_is_the_one_the_ceiling_check_assumes(self):
        text = (BIN / WAIT).read_text(encoding="utf-8")

        self.assertIn(f"--max-time {REQUEST_CAP_S} ", text)

    def test_refuses_a_job_id_that_is_not_one(self):
        for job_id in ("", "../jobs", "a b"):
            with self.subTest(job_id=job_id):
                result = run(command(WAIT, job_id))

                self.assertEqual(result.completed.returncode, 64, output(result.completed))
                self.assertEqual(result.calls, [])


class DelegateCancelTest(unittest.TestCase):
    def test_cancel_sends_delete_for_the_job(self):
        cancelled = job("cancelled")
        with StubServer({("DELETE", JOB_PATH): cancelled}) as server:
            completed = run(command("bipolar-delegate-cancel", JOB_ID), BIPOLAR_URL=server.url).completed

        self.assertEqual(completed.returncode, 0, output(completed))
        self.assertEqual([(r.method, r.path, r.api_key) for r in server.requests], [("DELETE", JOB_PATH, "test-key")])
        self.assertEqual(completed.stdout.splitlines()[-2:], [cancelled[1], "HTTP 200"])

    def test_cancel_of_a_job_already_gone_shows_the_404(self):
        with StubServer({}) as server:
            completed = run(command("bipolar-delegate-cancel", JOB_ID), BIPOLAR_URL=server.url).completed

        self.assertEqual(completed.stdout.splitlines()[-1], "HTTP 404")


if __name__ == "__main__":
    unittest.main()
