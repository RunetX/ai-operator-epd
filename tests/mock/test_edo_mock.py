"""Проверки мока оператора ЭДО без 1С: ответы на отправку титула в каждом режиме и журнал.

    python -m unittest tests.mock.test_edo_mock -v
"""

import json
import os
import sys
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edo_mock  # noqa: E402

PORT = 8892
TITLE = {"etrn": "e5a1", "title": "T1", "file_id": "ON_TRNACLGROT_A_B_C_0_20261004_X", "workflow_id": "w1"}


def post(path, payload):
    request = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", json.dumps(payload).encode("utf-8"),
                                     {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def journal():
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/_mock/journal", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


class EdoMockTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = edo_mock.start(PORT)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        post("/_mock/reset", {})

    def test_send_ok_by_default(self):
        answer = post("/send", TITLE)
        self.assertTrue(answer["ok"])
        self.assertTrue(answer["message_id"])
        self.assertEqual(journal()[0]["body"], TITLE)

    def test_error_modes(self):
        post("/_mock/mode", {"send": "error"})
        answer = post("/send", TITLE)
        self.assertFalse(answer["ok"])
        self.assertTrue(answer["blocking"])
        post("/_mock/mode", {"send": "transient"})
        answer = post("/send", TITLE)
        self.assertFalse(answer["blocking"])
        self.assertIn("временно", answer["text"])
        self.assertEqual(len(journal()), 2)

    def test_unknown_mode_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            post("/_mock/mode", {"send": "maybe"})
        self.assertEqual(error.exception.code, 400)

    def test_reset_clears_journal_and_mode(self):
        post("/_mock/mode", {"send": "error"})
        post("/send", TITLE)
        post("/_mock/reset", {})
        self.assertEqual(journal(), [])
        self.assertTrue(post("/send", TITLE)["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
