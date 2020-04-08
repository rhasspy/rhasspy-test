"""Natural language understanding tests (English)."""
import os
import sys
import unittest
from uuid import uuid4

import requests
from rhasspyhermes.nlu import NluIntent, NluIntentNotRecognized


class NluEnglishTests(unittest.TestCase):
    """Test natural language understanding (English)"""

    def setUp(self):
        self.http_port = os.environ.get("RHASSPY_HTTP_PORT", 12101)
        self.http_host = os.environ.get("RHASSPY_HTTP_HOST", "localhost")

    def api_url(self, fragment):
        return f"http://{self.http_host}:{self.http_port}/api/{fragment}"

    def check_status(self, response):
        if response.status_code != 200:
            print(response.text, file=sys.stderr)

        response.raise_for_status()

    def test_http_text_to_intent(self):
        """Test text-to-intent HTTP endpoint"""
        response = requests.post(
            self.api_url("text-to-intent"), data="set bedroom light to BLUE"
        )
        self.check_status(response)

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
        self.check_status(response)

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
        self.check_status(response)

        result = response.json()
        self.assertEqual(result["type"], "intent")

        nlu_intent = NluIntent.from_dict(result["value"])

        # Original text with upper-case COLOR
        self.assertEqual(nlu_intent.raw_input, "set bedroom light to BLUE")

        # Case-corrected text
        self.assertEqual(nlu_intent.input, "set bedroom light to blue")

        # Intent name and slots
        self.assertEqual(nlu_intent.intent.intent_name, "ChangeLightColor")

        slots_by_name = {slot.slot_name: slot for slot in nlu_intent.slots}
        self.assertIn("name", slots_by_name)
        self.assertEqual(slots_by_name["name"].value["value"], "bedroom light")

        self.assertIn("color", slots_by_name)
        self.assertEqual(slots_by_name["color"].value["value"], "blue")

    def test_http_text_to_intent_hermes_failure(self):
        """Test recognition failure with text-to-intent HTTP endpoint (Hermes format)"""
        response = requests.post(
            self.api_url("text-to-intent"),
            data="not a valid sentence",
            params={"outputFormat": "hermes"},
        )
        self.check_status(response)

        result = response.json()
        self.assertEqual(result["type"], "intentNotRecognized")

        # Different type
        not_recognized = NluIntentNotRecognized.from_dict(result["value"])

        # Input carried forward
        self.assertEqual(not_recognized.input, "not a valid sentence")

    def test_http_text_to_intent_custom_entity(self):
        """Test text-to-intent HTTP endpoint with custom entity"""
        custom_entity = str(uuid4())
        custom_value = str(uuid4())

        response = requests.post(
            self.api_url("text-to-intent"),
            data="set bedroom light to BLUE",
            params={"entity": custom_entity, "value": custom_value},
        )
        self.check_status(response)

        result = response.json()

        # Check custom entity
        self.assertEqual(result["slots"][custom_entity], custom_value)

        found_entity = False
        for entity in result["entities"]:
            if entity.get("entity", "") == custom_entity:
                found_entity = True
                self.assertEqual(entity.get("value", ""), custom_value)

        self.assertTrue(found_entity)

    def test_http_nlu_new_slot_value(self):
        """Test recognition with a new slot value"""
        response = requests.post(
            self.api_url("text-to-intent"),
            data="set bedroom light to purple",
            params={"outputFormat": "hermes"},
        )
        self.check_status(response)

        # Shouldn't exist yet
        result = response.json()
        self.assertEqual(result["type"], "intentNotRecognized")

        response = requests.get(self.api_url("slots/color"))
        self.check_status(response)
        original_colors = response.json()

        # Add purple to color slot
        response = requests.post(self.api_url("slots/color"), json=["purple"])
        self.check_status(response)

        # Re-train
        response = requests.post(self.api_url("train"))
        self.check_status(response)

        # Try again
        response = requests.post(
            self.api_url("text-to-intent"),
            data="set bedroom light to purple",
            params={"outputFormat": "hermes"},
        )
        self.check_status(response)

        result = response.json()
        self.assertEqual(result["type"], "intent")

        nlu_intent = NluIntent.from_dict(result["value"])

        # Intent name and slots
        self.assertEqual(nlu_intent.intent.intent_name, "ChangeLightColor")

        slots_by_name = {slot.slot_name: slot for slot in nlu_intent.slots}
        self.assertIn("name", slots_by_name)
        self.assertEqual(slots_by_name["name"].value["value"], "bedroom light")

        self.assertIn("color", slots_by_name)
        self.assertEqual(slots_by_name["color"].value["value"], "purple")

        # Restore colors
        response = requests.post(
            self.api_url("slots/color"),
            json=original_colors,
            params={"overwriteAll": "true"},
        )
        self.check_status(response)

        # Re-train
        response = requests.post(self.api_url("train"))
        self.check_status(response)

    def test_http_nlu_new_slot(self):
        """Test recognition with a new slot"""
        response = requests.post(
            self.api_url("text-to-intent"),
            data="what is the weather like in Germany",
            params={"outputFormat": "hermes"},
        )
        self.check_status(response)

        # Shouldn't exist yet
        result = response.json()
        self.assertEqual(result["type"], "intentNotRecognized")

        # Add new slot
        response = requests.post(
            self.api_url("slots/location"), json=["Germany", "France"]
        )
        self.check_status(response)

        # Add new intent
        response = requests.get(
            self.api_url("sentences"), headers={"Accept": "application/json"}
        )
        self.check_status(response)
        sentences = response.json()

        sentences[
            "intents/weather.ini"
        ] = "[GetWeather]\nwhat is the weather like in ($location){location}\n"

        # Save sentences
        response = requests.post(self.api_url("sentences"), json=sentences)
        self.check_status(response)

        # Re-train
        response = requests.post(self.api_url("train"))
        self.check_status(response)

        # Should work now
        response = requests.post(
            self.api_url("text-to-intent"),
            data="what is the weather like in Germany",
            params={"outputFormat": "hermes"},
        )
        self.check_status(response)

        result = response.json()
        self.assertEqual(result["type"], "intent")

        nlu_intent = NluIntent.from_dict(result["value"])

        # Intent name and slots
        self.assertEqual(nlu_intent.intent.intent_name, "GetWeather")

        slots_by_name = {slot.slot_name: slot for slot in nlu_intent.slots}
        self.assertIn("location", slots_by_name)
        self.assertEqual(slots_by_name["location"].value["value"], "Germany")

        # Remove slot
        response = requests.post(
            self.api_url("slots/location"), json=[], params={"overwrite_all": "true"}
        )
        self.check_status(response)

        # Remove sentences
        sentences["intents/weather.ini"] = ""
        response = requests.post(self.api_url("sentences"), json=sentences)
        self.check_status(response)

        # Re-train
        response = requests.post(self.api_url("train"))
        self.check_status(response)
