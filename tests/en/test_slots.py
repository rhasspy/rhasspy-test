"""Named entity/slots tests."""
import os
import sys
import unittest

import requests


class SlotsEnglishTests(unittest.TestCase):
    """Test slots (English)"""

    def setUp(self):
        self.http_port = os.environ.get("RHASSPY_HTTP_PORT", 12101)
        self.http_host = os.environ.get("RHASSPY_HTTP_HOST", "localhost")

    def api_url(self, fragment):
        return f"http://{self.http_host}:{self.http_port}/api/{fragment}"

    def check_status(self, response):
        if response.status_code != 200:
            print(response.text, file=sys.stderr)

        response.raise_for_status()

    def test_http_get_slot(self):
        """Test slots GET HTTP endpoint"""
        response = requests.get(self.api_url("slots"))
        self.check_status(response)

        slots = response.json()

        # Only color slot should be there
        self.assertEqual(len(slots), 1, slots)
        colors = set(slots.get("color", {}))
        self.assertEqual(colors, {"red", "green", "blue"})

        # Test single slot GET
        response = requests.get(self.api_url("slots/color"))
        self.check_status(response)

        colors2 = set(response.json())
        self.assertEqual(colors, colors2)

        # Test absent slot
        response = requests.get(self.api_url("slots/does-not-exist"))
        self.check_status(response)

        # Expect empty list
        self.assertEqual(response.json(), [])

    def test_http_modify_slot(self):
        """Test slots POST HTTP endpoint"""

        # Add purple
        response = requests.post(self.api_url("slots/color"), json=["purple"])
        self.check_status(response)

        # Check that it's there
        response = requests.get(self.api_url("slots/color"))
        self.check_status(response)
        colors = set(response.json())
        self.assertEqual(colors, {"red", "green", "blue", "purple"})

        # Remove purple
        colors.discard("purple")
        response = requests.post(
            self.api_url("slots/color"),
            json=list(colors),
            params={"overwriteAll": "true"},
        )
        self.check_status(response)

        # Check that it's gone
        response = requests.get(self.api_url("slots/color"))
        self.check_status(response)
        colors2 = set(response.json())
        self.assertEqual(colors, colors2)

    def test_http_add_slot(self):
        """Test slots POST HTTP endpoint"""

        # Add room
        rooms = {"living room", "kitchen", "bedroom"}
        response = requests.post(self.api_url("slots/room"), json=list(rooms))
        self.check_status(response)

        # Check that it's there
        response = requests.get(self.api_url("slots/room"))
        self.check_status(response)
        rooms2 = set(response.json())
        self.assertEqual(rooms, rooms2)

        # Remove room
        response = requests.post(
            self.api_url("slots/room"), json=[], params={"overwriteAll": "true"}
        )
        self.check_status(response)

        # Check that it's gone
        response = requests.get(self.api_url("slots"))
        self.check_status(response)
        slots = response.json()
        self.assertNotIn("room", slots)
