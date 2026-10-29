"""Small automated tests that can be run with python -m unittest."""

import tempfile
import unittest
from pathlib import Path

import app as travel_app
from knowledge_base import DESTINATIONS
from recommender import backward_chain_recommendation, forward_chain


class TravelAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_folder = tempfile.TemporaryDirectory()
        self.old_database = travel_app.app.config["DATABASE"]
        self.old_testing = travel_app.app.config.get("TESTING", False)
        travel_app.app.config["DATABASE"] = (
            Path(self.temp_folder.name) / "test-travel.db"
        )
        travel_app.app.config["TESTING"] = True
        travel_app.init_db()
        self.client = travel_app.app.test_client()

    def tearDown(self):
        travel_app.app.config["DATABASE"] = self.old_database
        travel_app.app.config["TESTING"] = self.old_testing
        self.temp_folder.cleanup()

    def csrf_token(self, page):
        self.client.get(page)
        with self.client.session_transaction() as browser_session:
            return browser_session["_csrf_token"]

    def register_user(self):
        token = self.csrf_token("/register")
        return self.client.post(
            "/register",
            data={
                "csrf_token": token,
                "username": "Asha",
                "email": "asha@example.com",
                "password": "simple-pass-123",
            },
            follow_redirects=True,
        )

    def test_ten_destinations_and_three_recommendations(self):
        self.assertEqual(len(DESTINATIONS), 10)
        preferences = {
            "budget": 18000,
            "trip_days": 5,
            "destination_type": "nature",
        }
        results = forward_chain(preferences)

        self.assertEqual(len(results), 3)
        self.assertGreaterEqual(results[0]["matched_count"], results[1]["matched_count"])
        proof = backward_chain_recommendation(results[0], preferences, 1)
        self.assertIn("top three", proof["goal"])
        self.assertEqual(len(proof["checks"]), 3)

    def test_dashboard_requires_a_signed_in_user(self):
        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_user_can_register_and_sign_in(self):
        response = self.register_user()

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Welcome, Asha.", response.data)
        self.client.post(
            "/logout",
            data={"csrf_token": self.csrf_token("/dashboard")},
        )

        login_token = self.csrf_token("/login")
        login_response = self.client.post(
            "/login",
            data={
                "csrf_token": login_token,
                "email": "asha@example.com",
                "password": "simple-pass-123",
            },
            follow_redirects=True,
        )

        self.assertEqual(login_response.status_code, 200)
        self.assertIn(b"Welcome, Asha.", login_response.data)

    def test_user_can_save_preferences_and_see_explanations(self):
        self.register_user()
        token = self.csrf_token("/plan-trip")
        response = self.client.post(
            "/plan-trip",
            data={
                "csrf_token": token,
                "budget": "18000",
                "trip_days": "5",
                "destination_type": "nature",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.count(b"Why Recommended?"), 3)
        self.assertIn(b"Backward chaining:", response.data)
        self.assertIn(b"IF your budget is at least", response.data)

    def test_forms_reject_an_invalid_csrf_token(self):
        self.csrf_token("/register")
        response = self.client.post(
            "/register",
            data={
                "csrf_token": "not-the-session-token",
                "username": "Asha",
                "email": "asha@example.com",
                "password": "simple-pass-123",
            },
        )

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
