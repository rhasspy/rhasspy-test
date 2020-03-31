"""Grapheme to phoneme tests."""
import json
import os
import sys
import unittest
from pathlib import Path
from uuid import uuid4

import requests
from rhasspyhermes.asr import AsrTextCaptured
from rhasspyhermes.nlu import NluIntent


class G2pEnglishTests(unittest.TestCase):
    """Test grapheme to phoneme (English)"""

    def setUp(self):
        self.http_host = os.environ.get("RHASSPY_HTTP_HOST", "localhost")
        self.http_port = os.environ.get("RHASSPY_HTTP_PORT", 12101)
        self.wav_bytes = Path("wav/en/turn_on_the_living_room_lamp.wav").read_bytes()

    def api_url(self, fragment):
        return f"http://{self.http_host}:{self.http_port}/api/{fragment}"

    def check_status(self, response):
        if response.status_code != 200:
            print(response.text, file=sys.stderr)

        response.raise_for_status()

    def test_lookup(self):
        """Test unknown word lookup"""
        response = requests.post(
            self.api_url("lookup"), data="raxacoricofallipatorius", params={"n": "1"}
        )
        self.check_status(response)

        result = response.json()
        self.assertFalse(result.get("in_dictionary", True))
        self.assertGreater(len(result.get("phonemes", "")), 0)

        pronunciations = result.get("pronunciations", [])
        self.assertGreater(len(pronunciations), 0)
        self.assertGreater(len(pronunciations[0]), 0)

    def test_custom_words(self):
        """Test unknown word lookup"""
        response = requests.get(self.api_url("custom-words"))
        self.check_status(response)
        current_custom_words = response.content.decode()

        # Overwrite custom words
        word = str(uuid4())
        response = requests.post(
            self.api_url("custom-words"), data=f"{word} P1 P2 P3\n"
        )
        self.check_status(response)

        # Re-train
        response = requests.post(self.api_url("train"))
        self.check_status(response)

        # Verify new pronunciation
        response = requests.post(self.api_url("lookup"), data=word)
        self.check_status(response)

        result = response.json()
        self.assertTrue(result.get("in_dictionary", False))
        self.assertEqual(result.get("pronunciations", []), ["P1 P2 P3"])

        # Restore custom words
        response = requests.post(
            self.api_url("custom-words"), data=current_custom_words
        )
        self.check_status(response)

        # Re-train
        response = requests.post(self.api_url("train"))
        self.check_status(response)
