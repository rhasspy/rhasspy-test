"""Test wake/ASR/NLU workflow."""
import asyncio
import logging
import os
import typing
import unittest
from uuid import uuid4

import paho.mqtt.client as mqtt

from rhasspyhermes.asr import AsrStartListening
from rhasspyhermes.audioserver import AudioPlayBytes, AudioPlayFinished
from rhasspyhermes.base import Message
from rhasspyhermes.client import HermesClient
from rhasspyhermes.dialogue import (
    DialogueAction,
    DialogueContinueSession,
    DialogueEndSession,
    DialogueSessionEnded,
    DialogueSessionStarted,
    DialogueSessionTerminationReason,
    DialogueStartSession,
)
from rhasspyhermes.nlu import NluIntentNotRecognized
from rhasspyhermes.wake import HotwordDetected

_LOGGER = logging.getLogger(__name__)


class DialogueManagerTests(unittest.TestCase):
    """Test dialogue manager with multiple satellites."""

    def setUp(self):
        self.base_id = "default"
        self.satellite_ids = ["satellite1", "satellite2"]
        self.session_ids = {}
        self.custom_data = {}
        self.continue_site_id = None

        self.loop = asyncio.get_event_loop()
        self.hermes = HermesClient(
            "dialogue",
            mqtt.Client(),
            site_ids=[self.base_id] + self.satellite_ids,
            loop=self.loop,
        )

        self.http_host = os.environ.get("RHASSPY_HTTP_HOST", "localhost")
        self.mqtt_port = int(os.environ.get("RHASSPY_MQTT_PORT") or 1883)
        self.mqtt_host = os.environ.get("RHASSPY_MQTT_HOST", self.http_host)

        self.hermes.mqtt_client.connect(self.mqtt_host, self.mqtt_port)
        self.hermes.mqtt_client.loop_start()

        self.events: typing.Dict[str, asyncio.Event] = {}

    def tearDown(self):
        self.hermes.mqtt_client.loop_stop()

    # -------------------------------------------------------------------------

    def test_basic_wake(self):
        """Call async_test_basic_wake"""
        self.loop.run_until_complete(self.async_test_basic_wake())

    async def async_test_basic_wake(self):
        """Test wake/asr/nlu workflow without a satellite"""
        for event_name in ["started", "ended"]:
            self.events[event_name] = asyncio.Event()

        # Wait until connected
        self.hermes.on_message = self.on_message_test_basic_wake
        await asyncio.wait_for(self.hermes.mqtt_connected_event.wait(), timeout=5)

        # Start listening
        self.hermes.subscribe(DialogueSessionStarted, DialogueSessionEnded)
        message_task = asyncio.create_task(self.hermes.handle_messages_async())

        # Send wake up signal
        self.hermes.publish(
            HotwordDetected(model_id="default", site_id=self.base_id),
            wakeword_id="default",
        )

        # Wait for up to 10 seconds
        await asyncio.wait_for(
            asyncio.gather(*[e.wait() for e in self.events.values()]), timeout=10
        )

        message_task.cancel()

    async def on_message_test_basic_wake(
        self,
        message: Message,
        site_id: typing.Optional[str] = None,
        session_id: typing.Optional[str] = None,
        topic: typing.Optional[str] = None,
    ):
        """Receive messages for test_basic_wake"""
        _LOGGER.debug(message)
        if isinstance(message, DialogueSessionStarted):
            self.events["started"].set()

            # Verify session was started on the base
            self.assertEqual(message.site_id, self.base_id)
            self.session_ids[message.site_id] = message.session_id

            # End the session
            yield DialogueEndSession(session_id=message.session_id)
        elif isinstance(message, DialogueSessionEnded):
            self.events["ended"].set()

            # Verify session was ended on the base
            self.assertEqual(message.site_id, self.base_id)

            self.assertEqual(self.session_ids[message.site_id], message.session_id)

        yield None

    # -------------------------------------------------------------------------

    def test_not_recognized(self):
        """Call async_test_not_recognized"""
        self.loop.run_until_complete(self.async_test_not_recognized())

    async def async_test_not_recognized(self):
        """Test start/end/not recognized without a satellite"""
        self.custom_data[self.base_id] = str(uuid4())

        for event_name in ["started", "ended"]:
            self.events[event_name] = asyncio.Event()

        # Wait until connected
        self.hermes.on_message = self.on_message_test_not_recognized
        await asyncio.wait_for(self.hermes.mqtt_connected_event.wait(), timeout=5)

        # Start listening
        self.hermes.subscribe(DialogueSessionStarted, DialogueSessionEnded)
        message_task = asyncio.create_task(self.hermes.handle_messages_async())

        # Start a new session
        self.hermes.publish(
            DialogueStartSession(
                init=DialogueAction(can_be_enqueued=False),
                site_id=self.base_id,
                custom_data=self.custom_data[self.base_id],
            )
        )

        # Wait for up to 10 seconds
        await asyncio.wait_for(
            asyncio.gather(*[e.wait() for e in self.events.values()]), timeout=10
        )

        message_task.cancel()

    async def on_message_test_not_recognized(
        self,
        message: Message,
        site_id: typing.Optional[str] = None,
        session_id: typing.Optional[str] = None,
        topic: typing.Optional[str] = None,
    ):
        """Receive messages for test_not_recognized"""
        _LOGGER.debug(message)
        if isinstance(message, DialogueSessionStarted):
            self.events["started"].set()

            # Verify session was started on the base
            self.assertEqual(message.site_id, self.base_id)
            self.assertEqual(message.custom_data, self.custom_data[message.site_id])
            self.session_ids[message.site_id] = message.session_id

            self.custom_data[message.site_id] = str(uuid4())

            # Publish an intent not recognized message to abort the session
            yield NluIntentNotRecognized(
                input="test intent",
                site_id=message.site_id,
                session_id=message.session_id,
                custom_data=self.custom_data[message.site_id],
            )
        elif isinstance(message, DialogueSessionEnded):
            self.events["ended"].set()

            # Verify session was aborted on the base
            self.assertEqual(message.site_id, self.base_id)
            self.assertEqual(
                message.termination.reason,
                DialogueSessionTerminationReason.INTENT_NOT_RECOGNIZED,
            )
            self.assertEqual(message.custom_data, self.custom_data[message.site_id])

            self.assertEqual(self.session_ids[message.site_id], message.session_id)

        yield None

    # -------------------------------------------------------------------------

    def test_multi_session(self):
        """Call async_test_multi_session"""
        self.loop.run_until_complete(self.async_test_multi_session())

    async def async_test_multi_session(self):
        """Test multiple sessions on multiple satellites without a satellite"""
        self.continue_site_id = self.satellite_ids[0]

        for site_id in [self.base_id] + self.satellite_ids:
            self.custom_data[site_id] = str(uuid4())

            for event_name in ["started", "ended"]:
                self.events[f"{site_id}_{event_name}"] = asyncio.Event()

        # Wait until connected
        self.hermes.on_message = self.on_message_test_multi_session
        await asyncio.wait_for(self.hermes.mqtt_connected_event.wait(), timeout=5)

        # Start listening
        self.hermes.subscribe(
            DialogueSessionStarted,
            DialogueSessionEnded,
            AudioPlayBytes,
            AsrStartListening,
        )

        message_task = asyncio.create_task(self.hermes.handle_messages_async())

        # Start a new session on the base and all satellites
        for site_id in [self.base_id] + self.satellite_ids:
            self.hermes.publish(
                DialogueStartSession(
                    init=DialogueAction(can_be_enqueued=False),
                    site_id=site_id,
                    custom_data=self.custom_data[site_id],
                )
            )

        # Wait for up to 10 seconds
        await asyncio.wait_for(
            asyncio.gather(*[e.wait() for e in self.events.values()]), timeout=10
        )

        message_task.cancel()

    async def on_message_test_multi_session(
        self,
        message: Message,
        site_id: typing.Optional[str] = None,
        session_id: typing.Optional[str] = None,
        topic: typing.Optional[str] = None,
    ):
        """Receive messages for test_multi_session"""
        if not isinstance(message, AudioPlayBytes):
            _LOGGER.debug(message)

        if isinstance(message, DialogueSessionStarted):
            # Verify session was started on the base or a satellite
            self.assertIn(message.site_id, [self.base_id] + self.satellite_ids)
            self.assertEqual(message.custom_data, self.custom_data[message.site_id])

            self.events[f"{message.site_id}_started"].set()

            self.session_ids[message.site_id] = message.session_id

            if message.site_id == self.continue_site_id:
                # Make session continue one more step
                self.custom_data[message.site_id] = "done"

                yield DialogueContinueSession(
                    session_id=message.session_id, custom_data="done"
                )
            else:
                self.custom_data[message.site_id] = str(uuid4())

                # Publish an intent not recognized message to abort the session
                yield NluIntentNotRecognized(
                    input=f"test intent (site={message.site_id})",
                    site_id=message.site_id,
                    session_id=message.session_id,
                    custom_data=self.custom_data[message.site_id],
                )
        elif isinstance(message, DialogueSessionEnded):

            # Verify session was aborted on the base or a satellite
            self.assertIn(message.site_id, [self.base_id] + self.satellite_ids)
            self.assertEqual(message.custom_data, self.custom_data[message.site_id])

            self.events[f"{message.site_id}_ended"].set()

            self.assertEqual(
                message.termination.reason,
                DialogueSessionTerminationReason.INTENT_NOT_RECOGNIZED,
            )

            self.assertEqual(self.session_ids[message.site_id], message.session_id)
        elif isinstance(message, AsrStartListening):
            # Follow on from continue session
            if (message.site_id == self.continue_site_id) and (
                self.custom_data[message.site_id] == "done"
            ):
                # Publish an intent not recognized message to abort the session
                yield NluIntentNotRecognized(
                    input=f"test intent (site={message.site_id})",
                    site_id=message.site_id,
                    session_id=message.session_id,
                )
        elif isinstance(message, AudioPlayBytes):
            yield (AudioPlayFinished(id=session_id), {"site_id": site_id})

        yield None
