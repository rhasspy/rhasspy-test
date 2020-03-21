"""Natural language understanding tests (English)."""
import json
import os
import unittest

import requests
from rhasspyhermes.nlu import NluIntent, NluIntentNotRecognized


class NluEnglishTests(unittest.TestCase):
    """Test natural language understanding (English)"""

    def setUp(self):
        self.http_port = os.environ.get("RHASSPY_HTTP_PORT", 12101)

    def api_url(self, fragment):
        return f"http://localhost:{self.http_port}/api/{fragment}"

    def test_http_text_to_intent(self):
        """Test text-to-intent HTTP endpoint"""
        response = requests.post(
            self.api_url("text-to-intent"), data="set bedroom light to BLUE"
        )
        response.raise_for_status()

        result = response.json()

        # Original text with upper-case COLOR
        self.assertEqual(result["raw_text"], "set bedroom light to BLUE")

        # Case-corrected text
        self.assertEqual(result["text"], "set bedroom light to blue")

        # Intent name and slots
        self.assertEqual(result["intent"]["name"], "ChangeLightColor")
        self.assertEqual(result["slots"]["name"], "bedroom light")
        self.assertEqual(result["slots"]["color"], "blue")

    def test_http_text_to_intent_failure(self):
        """Test recognition failure with text-to-intent HTTP endpoint"""
        response = requests.post(
            self.api_url("text-to-intent"), data="not a valid sentence"
        )
        response.raise_for_status()

        result = response.json()

        self.assertEqual(result["raw_text"], "not a valid sentence")
        self.assertEqual(result["text"], "not a valid sentence")

        # Empty intent name and no slots
        self.assertEqual(result["intent"]["name"], "")
        self.assertEqual(len(result["slots"]), 0)

    def test_http_text_to_intent_hermes(self):
        """Test text-to-intent HTTP endpoint (Hermes format)"""
        response = requests.post(
            self.api_url("text-to-intent"),
            data="set bedroom light to BLUE",
            params={"outputFormat": "hermes"},
        )
        response.raise_for_status()

        result = response.json()
        self.assertEqual(result["type"], "intent")

        nlu_intent = NluIntent.from_dict(result["value"])

        # Original text with upper-case COLOR
        self.assertEqual(nlu_intent.raw_input, "set bedroom light to BLUE")

        # Case-corrected text
        self.assertEqual(nlu_intent.input, "set bedroom light to blue")

        # Intent name and slots
        self.assertEqual(nlu_intent.intent.intentName, "ChangeLightColor")

        slots_by_name = {slot.slotName: slot for slot in nlu_intent.slots}
        self.assertIn("name", slots_by_name)
        self.assertEqual(slots_by_name["name"].value, "bedroom light")

        self.assertIn("color", slots_by_name)
        self.assertEqual(slots_by_name["color"].value, "blue")

    def test_http_text_to_intent_hermes_failure(self):
        """Test recognition failure with text-to-intent HTTP endpoint (Hermes format)"""
        response = requests.post(
            self.api_url("text-to-intent"),
            data="not a valid sentence",
            params={"outputFormat": "hermes"},
        )
        response.raise_for_status()

        result = response.json()
        self.assertEqual(result["type"], "intentNotRecognized")

        # Different type
        not_recognized = NluIntentNotRecognized.from_dict(result["value"])

        # Input carried forward
        self.assertEqual(not_recognized.input, "not a valid sentence")

    def test_http_nlu_new_slot_value(self):
        """Test recognition with a new slot value"""
        response = requests.post(
            self.api_url("text-to-intent"),
            data="set bedroom light to purple",
            params={"outputFormat": "hermes"},
        )
        response.raise_for_status()

        # Shouldn't exist yet
        result = response.json()
        self.assertEqual(result["type"], "intentNotRecognized")

        response = requests.get(self.api_url("slots/color"))
        response.raise_for_status()
        original_colors = response.json()

        # Add purple to color slot
        response = requests.post(self.api_url("slots/color"), json=["purple"])
        response.raise_for_status()

        # Re-train
        response = requests.post(self.api_url("train"))
        response.raise_for_status()

        # Try again
        response = requests.post(
            self.api_url("text-to-intent"),
            data="set bedroom light to purple",
            params={"outputFormat": "hermes"},
        )
        response.raise_for_status()

        result = response.json()
        self.assertEqual(result["type"], "intent")

        nlu_intent = NluIntent.from_dict(result["value"])

        # Intent name and slots
        self.assertEqual(nlu_intent.intent.intentName, "ChangeLightColor")

        slots_by_name = {slot.slotName: slot for slot in nlu_intent.slots}
        self.assertIn("name", slots_by_name)
        self.assertEqual(slots_by_name["name"].value, "bedroom light")

        self.assertIn("color", slots_by_name)
        self.assertEqual(slots_by_name["color"].value, "purple")

        # Restore colors
        response = requests.post(
            self.api_url("slots/color"),
            json=original_colors,
            params={"overwrite_all": "true"},
        )
        response.raise_for_status()

        # Re-train
        response = requests.post(self.api_url("train"))
        response.raise_for_status()

    def test_http_nlu_new_slot(self):
        """Test recognition with a new slot"""
        response = requests.post(
            self.api_url("text-to-intent"),
            data="what is the weather like in Germany",
            params={"outputFormat": "hermes"},
        )
        response.raise_for_status()

        # Shouldn't exist yet
        result = response.json()
        self.assertEqual(result["type"], "intentNotRecognized")

        # Add new slot
        response = requests.post(
            self.api_url("slots/location"), json=["Germany", "France"]
        )
        response.raise_for_status()

        # Add new intent
        response = requests.get(
            self.api_url("sentences"), headers={"Accept": "application/json"}
        )
        response.raise_for_status()
        sentences = response.json()

        sentences[
            "intents/weather.ini"
        ] = "[GetWeather]\nwhat is the weather like in ($location){location}\n"

        # Save sentences
        response = requests.post(self.api_url("sentences"), json=sentences)
        response.raise_for_status()

        # Re-train
        response = requests.post(self.api_url("train"))
        response.raise_for_status()

        # Should work now
        response = requests.post(
            self.api_url("text-to-intent"),
            data="what is the weather like in Germany",
            params={"outputFormat": "hermes"},
        )
        response.raise_for_status()

        result = response.json()
        self.assertEqual(result["type"], "intent")

        nlu_intent = NluIntent.from_dict(result["value"])

        # Intent name and slots
        self.assertEqual(nlu_intent.intent.intentName, "GetWeather")

        slots_by_name = {slot.slotName: slot for slot in nlu_intent.slots}
        self.assertIn("location", slots_by_name)
        self.assertEqual(slots_by_name["location"].value, "Germany")

        # Remove slot
        response = requests.post(
            self.api_url("slots/location"), json=[], params={"overwrite_all": "true"}
        )
        response.raise_for_status()

        # Remove sentences
        sentences["intents/weather.ini"] = ""
        response = requests.post(self.api_url("sentences"), json=sentences)
        response.raise_for_status()

        # Re-train
        response = requests.post(self.api_url("train"))
        response.raise_for_status()
