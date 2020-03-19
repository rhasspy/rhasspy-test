import asyncio
import io
import json
import logging
import os
import threading
import typing
import unittest
from pathlib import Path

import paho.mqtt.client as mqtt
from rhasspyhermes.base import Message
from rhasspyhermes.asr import AsrTextCaptured
from rhasspyhermes.audioserver import AudioFrame
from rhasspyhermes.client import HermesClient
from rhasspyhermes.nlu import NluIntent
from rhasspyhermes.wake import HotwordDetected

_LOGGER = logging.getLogger(__name__)


class WakeAsrMqttEnglishTests(unittest.TestCase):
    """Test wake word and automated speech recognition (English)"""

    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.hermes = HermesClient("wake_asr_en", mqtt.Client(), loop=self.loop)

        mqtt_port = int(os.environ.get("RHASSPY_MQTT_PORT") or 1883)
        self.hermes.mqtt_client.connect("localhost", mqtt_port)
        self.hermes.mqtt_client.loop_start()
        self.done_event = threading.Event()

        wake_system = os.environ.get("WAKE_SYSTEM") or "porcupine"
        self.wav_path = Path(
            f"wav/wake/en/{wake_system}_turn_on_the_living_room_lamp.wav"
        )
        self.wav_bytes = self.wav_path.read_bytes()

    def tearDown(self):
        self.hermes.mqtt_client.loop_stop()

    # -------------------------------------------------------------------------

    def test_1(self):
        """Test 1"""
        self.hotword_detected = None
        self.text_captured = None
        self.nlu_intent = None

        self.hermes.on_message = self.on_message_test_1
        self.hermes.subscribe(HotwordDetected, AsrTextCaptured, NluIntent)

        # Send audio with realtime delays
        _LOGGER.debug("Sending %s", self.wav_path)
        with io.BytesIO(self.wav_bytes) as wav_io:
            for chunk in AudioFrame.iter_wav_chunked(wav_io, 4096, live_delay=True):
                self.hermes.publish(AudioFrame(chunk), siteId="default")

        # Run event loop.
        # Timeout after 10 seconds.
        self.loop.call_later(10, self.stop_test)
        self.loop.run_forever()

        # Verify hotword
        self.assertIsNotNone(self.hotword_detected, "No hotword detected")

        # Verify transcription
        self.assertIsNotNone(self.text_captured, "No text captured")
        self.assertEqual(self.text_captured.text, "turn on the living room lamp")

        # Verify intent
        self.assertIsNotNone(self.nlu_intent, "No intent recognized")
        self.assertEqual(self.nlu_intent.intent.intentName, "ChangeLightState")

        slots = {s.slotName: s.value for s in self.nlu_intent.slots}
        self.assertEqual(slots.get("state"), "on")
        self.assertEqual(slots.get("name"), "living room lamp")

    def stop_test(self):
        self.hermes.stop()
        self.loop.stop()

    async def on_message_test_1(
        self,
        message: Message,
        siteId: typing.Optional[str] = None,
        sessionId: typing.Optional[str] = None,
        topic: typing.Optional[str] = None,
    ):
        """Test 1"""
        try:
            if isinstance(message, HotwordDetected):
                self.hotword_detected = message
            elif isinstance(message, AsrTextCaptured):
                self.text_captured = message
            elif isinstance(message, NluIntent):
                self.nlu_intent = message
        finally:
            if all((self.hotword_detected, self.text_captured, self.nlu_intent)):
                self.stop_test()
