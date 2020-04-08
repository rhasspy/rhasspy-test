"""Test wake/ASR/NLU workflow."""
import asyncio
import io
import logging
import os
import typing
import unittest
from pathlib import Path

import paho.mqtt.client as mqtt
from rhasspyhermes.asr import AsrTextCaptured
from rhasspyhermes.audioserver import AudioFrame
from rhasspyhermes.base import Message
from rhasspyhermes.client import HermesClient
from rhasspyhermes.nlu import NluIntent
from rhasspyhermes.wake import HotwordDetected

_LOGGER = logging.getLogger(__name__)


class WakeAsrMqttEnglishTests(unittest.TestCase):
    """Test wake word and automated speech recognition (English)"""

    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.hermes = HermesClient("wake_asr_en", mqtt.Client(), loop=self.loop)

        self.http_host = os.environ.get("RHASSPY_HTTP_HOST", "localhost")
        self.mqtt_port = int(os.environ.get("RHASSPY_MQTT_PORT") or 1883)
        self.mqtt_host = os.environ.get("RHASSPY_MQTT_HOST", self.http_host)

        self.hermes.mqtt_client.connect(self.mqtt_host, self.mqtt_port)
        self.hermes.mqtt_client.loop_start()

        self.wake_system = os.environ.get("WAKE_SYSTEM") or "porcupine"
        self.wav_path = Path(
            f"wav/wake/en/{self.wake_system}_turn_on_the_living_room_lamp.wav"
        )
        self.wav_bytes = self.wav_path.read_bytes()

        self.ready_event = asyncio.Event()
        self.done_event = asyncio.Event()

    def tearDown(self):
        self.hermes.mqtt_client.loop_stop()

    # -------------------------------------------------------------------------

    def test_workflow(self):
        """Call async_test_workflow"""
        self.loop.run_until_complete(self.async_test_workflow())

    async def async_test_workflow(self):
        """Test wake/asr/nlu workflow"""
        self.hotword_detected = None
        self.text_captured = None
        self.nlu_intent = None

        # Wait until connected
        self.hermes.on_message = self.on_message_test_workflow
        await asyncio.wait_for(self.hermes.mqtt_connected_event.wait(), timeout=5)

        # Start listening
        self.hermes.subscribe(HotwordDetected, AsrTextCaptured, NluIntent)
        message_task = asyncio.create_task(self.hermes.handle_messages_async())

        # Send audio with realtime delays
        _LOGGER.debug("Sending %s", self.wav_path)
        with io.BytesIO(self.wav_bytes) as wav_io:
            for chunk in AudioFrame.iter_wav_chunked(wav_io, 4096, live_delay=True):
                self.hermes.publish(AudioFrame(wav_bytes=chunk), site_id="default")

        # Wait for up to 10 seconds
        await asyncio.wait_for(self.done_event.wait(), timeout=10)

        # Verify hotword
        self.assertIsNotNone(
            self.hotword_detected,
            f"No hotword detected (system={self.wake_system}, wav={self.wav_path})",
        )

        # Verify transcription
        self.assertIsNotNone(self.text_captured, "No text captured")
        self.assertEqual(self.text_captured.text, "turn on the living room lamp")

        # Verify intent
        self.assertIsNotNone(self.nlu_intent, "No intent recognized")
        self.assertEqual(self.nlu_intent.intent.intent_name, "ChangeLightState")

        slots = {s.slot_name: s.value["value"] for s in self.nlu_intent.slots}
        self.assertEqual(slots.get("state"), "on")
        self.assertEqual(slots.get("name"), "living room lamp")

        message_task.cancel()

    async def on_message_test_workflow(
        self,
        message: Message,
        site_id: typing.Optional[str] = None,
        session_id: typing.Optional[str] = None,
        topic: typing.Optional[str] = None,
    ):
        """Receive messages for test_workflow"""
        _LOGGER.debug(message)
        if isinstance(message, HotwordDetected):
            self.hotword_detected = message
        elif isinstance(message, AsrTextCaptured):
            self.text_captured = message
        elif isinstance(message, NluIntent):
            self.nlu_intent = message

        if self.hotword_detected and self.text_captured and self.nlu_intent:
            self.done_event.set()

        yield None
