"""Тесты: python3 -m unittest -v test_app"""
import csv
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

os.environ["USERS_FILE"] = os.path.join(tempfile.mkdtemp(), "users.json")

import server  # noqa: E402
from forecast_core import DATA_DIR, ForecastError, Forecaster  # noqa: E402


class CoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fc = Forecaster(os.path.join(DATA_DIR, "seasonal_forecast.csv"))

    def test_formula_matches_spec(self):
        # MOW-AER 2026-06-01 в seasonal_forecast.csv: 0.5_base_demand = 775, seats = 900
        r = self.fc.forecast("Москва", "Сочи", "2026-06-01", 10000)
        want = 775 - 0.141 * (10000 - 9000)
        self.assertAlmostEqual(r["want"], want)
        self.assertAlmostEqual(r["buy"], min(900, max(0, want)))
        self.assertEqual(r["seats"], 900)

    def test_base_price_gives_base_demand(self):
        r = self.fc.forecast("MOW", "AER", "2026-06-01", 9000)
        self.assertEqual(r["want"], 775)

    def test_sales_capped_by_seats_and_zero(self):
        cheap = self.fc.forecast("MOW", "LED", "2026-06-05", 100)
        self.assertEqual(cheap["buy"], cheap["seats"])
        expensive = self.fc.forecast("MOW", "LED", "2026-06-05", 1_000_000)
        self.assertEqual(expensive["buy"], 0)

    def test_median_scenario_equals_simple_forecast(self):
        r = self.fc.forecast("MOW", "KGD", "2026-06-20", 8000)
        self.assertEqual(r["scenarios"][4]["quantile"], 0.5)
        self.assertEqual(r["scenarios"][4]["want"], r["want"])

    def test_bad_inputs(self):
        for args in [("MOW", "XXX", "2026-06-01", 1), ("AER", "MOW", "2026-06-01", 1),
                     ("MOW", "AER", "2026-08-01", 1), ("MOW", "AER", "01.06.2026", 1),
                     ("MOW", "AER", "2026-06-01", "abc"), ("MOW", "AER", "2026-06-01", -5)]:
            with self.assertRaises(ForecastError, msg=args):
                self.fc.forecast(*args)

    def test_all_rows_loaded(self):
        with open(os.path.join(DATA_DIR, "seasonal_forecast.csv"), encoding="utf-8") as f:
            self.assertEqual(len(self.fc.rows), sum(1 for _ in csv.DictReader(f)))


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def call(self, path, body=None, cookie=None):
        req = urllib.request.Request(self.base + path, method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})})
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read()), res.headers.get("Set-Cookie")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read()), None

    def test_flow(self):
        q = {"origin": "MOW", "destination": "AER", "date": "2026-06-12", "price": 9000}
        self.assertEqual(self.call("/api/forecast", q)[0], 401)                       # без входа нельзя
        st, body, cookie = self.call("/api/register", {"login": "tester", "password": "secret1"})
        self.assertEqual(st, 200)
        self.assertEqual(self.call("/api/register", {"login": "Tester", "password": "secret1"})[0], 400)  # занят
        self.assertEqual(self.call("/api/login", {"login": "tester", "password": "wrong!!"})[0], 401)
        st, body, cookie = self.call("/api/login", {"login": "tester", "password": "secret1"})
        self.assertEqual(st, 200)
        session = cookie.split(";")[0]
        self.assertEqual(self.call("/api/me", cookie=session)[1]["login"], "tester")
        st, r, _ = self.call("/api/forecast", q, cookie=session)
        self.assertEqual(st, 200)
        self.assertEqual(len(r["scenarios"]), 9)
        self.assertEqual(self.call("/api/forecast", {**q, "date": "2030-01-01"}, cookie=session)[0], 400)
        self.call("/api/logout", {}, cookie=session)
        self.assertEqual(self.call("/api/forecast", q, cookie=session)[0], 401)

    def test_password_not_stored_plain(self):
        self.call("/api/register", {"login": "plain_check", "password": "mypassword"})
        with open(os.environ["USERS_FILE"], encoding="utf-8") as f:
            self.assertNotIn("mypassword", f.read())


if __name__ == "__main__":
    unittest.main()
