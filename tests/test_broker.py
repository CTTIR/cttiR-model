import copy
import http.client
import json
import subprocess
import threading
import time
import unittest
from pathlib import Path

from cttir_model.broker import Broker, FixtureEndpoint
from cttir_model.errors import ProjectError
from cttir_model.serving import LocalServer
from test_evidence import corpus, request


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.c = corpus()
        self.request = request(self.c)
        self.endpoint = FixtureEndpoint()
        self.broker = Broker(self.c, self.endpoint, self.endpoint)

    def test_consult_and_duplicate_do_not_repeat_calls(self):
        first = self.broker.run(self.request, True)
        self.assertEqual(first["routing"]["specialist_calls"], 1)
        first["proposal"]["summary"] = "caller mutation"
        second = self.broker.run(self.request, True)
        self.assertNotEqual(first["proposal"]["summary"], second["proposal"]["summary"])
        self.assertTrue(second["runtime"]["fixture_only"])
        with self.assertRaisesRegex(ProjectError, "different content"):
            self.broker.run({**self.request, "instruction": "different"}, True)

    def test_missing_evidence_abstains_and_missing_model_errors(self):
        broker = Broker(self.c)
        result = broker.run({**self.request, "evidence_ids": []})
        self.assertEqual(result["routing"]["specialist_calls"], 0)
        with self.assertRaises(ProjectError):
            broker.run({**self.request, "request_id": "with-evidence"})
        self.assertFalse(broker.health()["model_ready"])

    def test_one_schema_repair_and_no_recursive_tools(self):
        class Repair(FixtureEndpoint):
            count = 0
            def generate(self, *args, **kwargs):
                self.count += 1
                return {} if self.count == 1 else super().generate(*args, **kwargs)
        endpoint = Repair()
        result = Broker(self.c, endpoint, endpoint).run(self.request)
        self.assertEqual(result["routing"]["repair_count"], 1)
        class BadSupervisor(FixtureEndpoint):
            def delegate(self, *args):
                return {"tool": "run_shell"}
        with self.assertRaisesRegex(ProjectError, "unapproved tool"):
            Broker(self.c, endpoint, BadSupervisor()).run(self.request, True)

    def test_repair_budget_is_finite(self):
        class Bad(FixtureEndpoint):
            count = 0
            def generate(self, *args):
                self.count += 1
                return {}
        endpoint = Bad()
        with self.assertRaises(ProjectError):
            Broker(self.c, endpoint).run(self.request)
        self.assertEqual(endpoint.count, 2)

    def test_cancellation_and_admission(self):
        entered = threading.Event()
        class Slow(FixtureEndpoint):
            def generate(self, req, evidence, token, repair=None):
                entered.set()
                while not token.event.wait(0.01):
                    token.check()
                token.check()
        broker = Broker(self.c, Slow())
        errors = []
        def run():
            try:
                broker.run(self.request)
            except ProjectError as exc:
                errors.append(exc.code)
        worker = threading.Thread(target=run)
        worker.start()
        self.assertTrue(entered.wait(2))
        with self.assertRaisesRegex(ProjectError, "already running"):
            broker.run({**self.request, "request_id": "second"})
        self.assertTrue(broker.cancel(self.request["request_id"]))
        worker.join(2)
        self.assertEqual(errors, ["cancelled"])
        self.assertFalse(worker.is_alive())


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = corpus()
        endpoint = FixtureEndpoint()
        cls.server = LocalServer(("127.0.0.1", 0), Broker(cls.c, endpoint, endpoint))
        cls.worker = threading.Thread(target=cls.server.serve_forever, kwargs={"poll_interval": 0.01})
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(2)

    def call(self, method, path, data=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        body = json.dumps(data) if data is not None else None
        conn.request(method, path, body, headers or {"Content-Type": "application/json"})
        response = conn.getresponse()
        result = (response.status, json.loads(response.read()))
        conn.close()
        return result

    def test_health_consult_and_cancellation(self):
        status, value = self.call("GET", "/health")
        self.assertEqual(status, 200)
        self.assertFalse(value["model_ready"])
        status, value = self.call("POST", "/v1/consult", request(self.c))
        self.assertEqual(status, 200)
        self.assertEqual(value["routing"]["mode"], "consult")
        status, value = self.call("DELETE", "/v1/requests/absent")
        self.assertFalse(value["cancelled"])

    def test_origin_and_body_guards(self):
        status, _ = self.call("GET", "/health", headers={"Origin": "https://bad.example"})
        self.assertEqual(status, 400)
        status, _ = self.call("POST", "/v1/consult", {"secret": "CANARY"})
        self.assertEqual(status, 422)
        status, _ = self.call("POST", "/v1/consult", "x" * 65537)
        self.assertEqual(status, 413)

    def test_r_client_against_live_fixture_service(self):
        import shutil
        if not shutil.which("Rscript"):
            self.skipTest("Rscript not installed; run R integration tier separately")
        probe = subprocess.run(["Rscript", "--vanilla", "-e",
                                "quit(status=if(requireNamespace('jsonlite',quietly=TRUE) && requireNamespace('curl',quietly=TRUE)) 0 else 1)"],
                               capture_output=True, timeout=5)
        if probe.returncode:
            self.skipTest("Declared R client dependencies not installed")
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(["Rscript", "--vanilla", str(root / "tests/r/client.R"),
                                 f"http://127.0.0.1:{self.server.server_port}", self.c.snapshot_id],
                                capture_output=True, text=True, timeout=15, cwd=root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
