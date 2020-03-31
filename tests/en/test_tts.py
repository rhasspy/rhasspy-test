import json
import os
import queue
import sys
import threading
import unittest
from uuid import uuid4

import paho.mqtt.client as mqtt
import requests
from rhasspyhermes.audioserver import (
    AudioPlayBytes,
    AudioPlayFinished,
    AudioToggleOff,
    AudioToggleOn,
)
from rhasspyhermes.tts import TtsSay, TtsSayFinished


class TtsEnglishTests(unittest.TestCase):
    """Test text to speech (English)"""

    def setUp(self):
        self.http_port = os.environ.get("RHASSPY_HTTP_PORT", 12101)
        self.http_host = os.environ.get("RHASSPY_HTTP_HOST", "localhost")
        self.mqtt_port = int(os.environ.get("RHASSPY_MQTT_PORT") or 1883)
        self.mqtt_host = os.environ.get("RHASSPY_MQTT_HOST", self.http_host)
        self.client = mqtt.Client()
        self.mqtt_messages = queue.Queue()

        def on_message(client, userdata, msg):
            self.mqtt_messages.put(msg)

        self.client.on_message = on_message

        connected_event = threading.Event()
        self.client.on_connect = lambda *args: connected_event.set()

        self.client.connect(self.mqtt_host, self.mqtt_port)
        self.client.loop_start()

        # Block until connected
        connected_event.wait(timeout=5)

        self.siteId = "default"
        self.sessionId = str(uuid4())

    def tearDown(self):
        self.client.loop_stop()

    def api_url(self, fragment):
        return f"http://{self.http_host}:{self.http_port}/api/{fragment}"

    def check_status(self, response):
        if response.status_code != 200:
            print(response.text, file=sys.stderr)

        response.raise_for_status()

    def test_http_mqtt_text_to_speech(self):
        """Test text-to-speech HTTP endpoint"""
        text = "This is a test."
        self.client.subscribe(TtsSay.topic())
        self.client.subscribe(AudioPlayBytes.topic(siteId=self.siteId))
        self.client.subscribe(TtsSayFinished.topic())

        response = requests.post(
            self.api_url("text-to-speech"),
            data=text,
            params={"siteId": self.siteId, "sessionId": self.sessionId},
        )
        self.check_status(response)

        wav_data = response.content
        self.assertGreater(len(wav_data), 0)

        # Check tts/say
        tts_say_msg = self.mqtt_messages.get(timeout=5)
        self.assertTrue(TtsSay.is_topic(tts_say_msg.topic))

        tts_say = TtsSay.from_dict(json.loads(tts_say_msg.payload))
        self.assertEqual(tts_say.siteId, self.siteId)
        self.assertEqual(tts_say.sessionId, self.sessionId)
        self.assertEqual(tts_say.text, text)

        # Check tts/sayFinished
        tts_finished_msg = self.mqtt_messages.get(timeout=5)
        self.assertTrue(TtsSayFinished.is_topic(tts_finished_msg.topic))

        tts_finished = TtsSayFinished.from_dict(json.loads(tts_finished_msg.payload))
        self.assertEqual(tts_finished.sessionId, self.sessionId)

        # Check audioServer/playBytes
        play_bytes_msg = self.mqtt_messages.get(timeout=5)
        self.assertTrue(AudioPlayBytes.is_topic(play_bytes_msg.topic))
        self.assertEqual(AudioPlayBytes.get_siteId(play_bytes_msg.topic), self.siteId)
        self.assertEqual(play_bytes_msg.payload, wav_data)

        # Ask for repeat
        response = requests.post(
            self.api_url("text-to-speech"), params={"repeat": "true"}
        )
        self.check_status(response)
        self.assertEqual(wav_data, response.content)

    def test_no_play(self):
        """Test text-to-speech HTTP endpoint with play=false"""
        text = "This is a test."
        self.client.subscribe(TtsSay.topic())
        self.client.subscribe(AudioPlayBytes.topic(siteId=self.siteId))
        self.client.subscribe(TtsSayFinished.topic())
        self.client.subscribe(AudioToggleOff.topic())
        self.client.subscribe(AudioToggleOn.topic())

        response = requests.post(
            self.api_url("text-to-speech"),
            data=text,
            params={
                "siteId": self.siteId,
                "sessionId": self.sessionId,
                "play": "false",
            },
        )
        self.check_status(response)

        wav_data = response.content
        self.assertGreater(len(wav_data), 0)

        # Check audioServer/toggleOff
        audio_off_msg = self.mqtt_messages.get(timeout=5)
        self.assertTrue(AudioToggleOff.is_topic(audio_off_msg.topic))

        audio_off = AudioToggleOff.from_dict(json.loads(audio_off_msg.payload))
        self.assertEqual(audio_off.siteId, self.siteId)

        # Check tts/say
        tts_say_msg = self.mqtt_messages.get(timeout=5)
        self.assertTrue(TtsSay.is_topic(tts_say_msg.topic))

        tts_say = TtsSay.from_dict(json.loads(tts_say_msg.payload))
        self.assertEqual(tts_say.siteId, self.siteId)
        self.assertEqual(tts_say.sessionId, self.sessionId)
        self.assertEqual(tts_say.text, text)

        # Check tts/sayFinished
        tts_finished_msg = self.mqtt_messages.get(timeout=5)
        self.assertTrue(TtsSayFinished.is_topic(tts_finished_msg.topic))

        tts_finished = TtsSayFinished.from_dict(json.loads(tts_finished_msg.payload))
        self.assertEqual(tts_finished.siteId, self.siteId)
        self.assertEqual(tts_finished.sessionId, self.sessionId)

        # Check audioServer/playBytes (will be ignored by audio output system)
        play_bytes_msg = self.mqtt_messages.get(timeout=5)
        self.assertTrue(AudioPlayBytes.is_topic(play_bytes_msg.topic))
        self.assertEqual(AudioPlayBytes.get_siteId(play_bytes_msg.topic), self.siteId)
        self.assertEqual(play_bytes_msg.payload, wav_data)

        # Check audioServer/toggleOn
        audio_on_msg = self.mqtt_messages.get(timeout=5)
        self.assertTrue(AudioToggleOn.is_topic(audio_on_msg.topic))

        audio_on = AudioToggleOn.from_dict(json.loads(audio_on_msg.payload))
        self.assertEqual(audio_on.siteId, self.siteId)
