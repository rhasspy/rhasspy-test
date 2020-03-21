import json
import os
import unittest

import requests


class SlotsEnglishTests(unittest.TestCase):
    """Test slots (English)"""

    def setUp(self):
        self.http_port = os.environ.get("RHASSPY_HTTP_PORT", 12101)

    def api_url(self, fragment):
        return f"http://localhost:{self.http_port}/api/{fragment}"

    def test_http_get_slot(self):
        """Test slots GET HTTP endpoint"""
        response = requests.get(self.api_url("slots"))
        response.raise_for_status()

        slots = response.json()

        # Only color slot should be there
        self.assertEqual(len(slots), 1)
        colors = set(slots.get("color", {}))
        self.assertEqual(colors, {"red", "green", "blue"})

        # Test single slot GET
        response = requests.get(self.api_url("slots/color"))
        response.raise_for_status()

        colors2 = set(response.json())
        self.assertEqual(colors, colors2)

        # Test absent slot
        response = requests.get(self.api_url("slots/does-not-exist"))
        response.raise_for_status()

        # Expect empty list
        self.assertEqual(response.json(), [])

    def test_http_modify_slot(self):
        """Test slots POST HTTP endpoint"""

        # Add purple
        response = requests.post(self.api_url("slots/color"), json=["purple"])
        response.raise_for_status()

        # Check that it's there
        response = requests.get(self.api_url("slots/color"))
        response.raise_for_status()
        colors = set(response.json())
        self.assertEqual(colors, {"red", "green", "blue", "purple"})

        # Remove purple
        colors.discard("purple")
        response = requests.post(
            self.api_url("slots/color"),
            json=list(colors),
            params={"overwrite_all": "true"},
        )
        response.raise_for_status()

        # Check that it's gone
        response = requests.get(self.api_url("slots/color"))
        response.raise_for_status()
        colors2 = set(response.json())
        self.assertEqual(colors, colors2)

    def test_http_add_slot(self):
        """Test slots POST HTTP endpoint"""

        # Add room
        rooms = {"living room", "kitchen", "bedroom"}
        response = requests.post(self.api_url("slots/room"), json=list(rooms))
        response.raise_for_status()

        # Check that it's there
        response = requests.get(self.api_url("slots/room"))
        response.raise_for_status()
        rooms2 = set(response.json())
        self.assertEqual(rooms, rooms2)

        # Remove room
        response = requests.post(
            self.api_url("slots/room"), json=[], params={"overwrite_all": "true"}
        )
        response.raise_for_status()

        # Check that it's gone
        response = requests.get(self.api_url("slots"))
        response.raise_for_status()
        slots = response.json()
        self.assertNotIn("room", slots)
