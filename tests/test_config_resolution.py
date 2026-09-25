import unittest

from shell_blocks import run_with_fakes
from test_delegate_json_body import submit_block

DELEGATE = "commands/delegate.md"
FILE_URL = "http://from-file:8000"
FILE_KEY = "file-key"
ENV_URL = "http://from-env:8000"
ENV_KEY = "env-key"
NOT_CONFIGURED = {"BIPOLAR_URL": "", "BIPOLAR_API_KEY": ""}
ONLY_ENV = {"BIPOLAR_URL": ENV_URL, "BIPOLAR_API_KEY": ENV_KEY}


def with_config_file(block, url=FILE_URL, key=FILE_KEY):
    write_config = (
        'mkdir -p "$HOME/.config/bipolar-cc"\n'
        f'printf "BIPOLAR_URL=%s\nBIPOLAR_API_KEY=%s\n" "{url}" "{key}" > "$HOME/.config/bipolar-cc/env"\n'
    )
    return write_config + block


def curl_calls(run):
    return [call for call in run.calls if call.startswith("curl ")]


class DelegateSubmitConfigTest(unittest.TestCase):
    def test_submit_reads_the_config_file_written_by_setup(self):
        run = run_with_fakes(with_config_file(submit_block()), **NOT_CONFIGURED)

        self.assertEqual(run.completed.returncode, 0, run.completed.stderr)
        post = curl_calls(run)[0]
        self.assertIn(f"{FILE_URL}/api/delegate/jobs", post)
        self.assertIn(f"x-api-key: {FILE_KEY}", post)

    def test_submit_keeps_environment_variables_over_the_file(self):
        run = run_with_fakes(with_config_file(submit_block()), **ONLY_ENV)

        post = curl_calls(run)[0]
        self.assertIn(f"{ENV_URL}/api/delegate/jobs", post)
        self.assertIn(f"x-api-key: {ENV_KEY}", post)

    def test_submit_refuses_without_any_config_before_any_request(self):
        run = run_with_fakes(submit_block(), **NOT_CONFIGURED)

        self.assertEqual(run.completed.returncode, 78, run.completed.stdout)
        self.assertIn("/bipolar:setup", run.completed.stdout)
        self.assertEqual(curl_calls(run), [])


if __name__ == "__main__":
    unittest.main()
