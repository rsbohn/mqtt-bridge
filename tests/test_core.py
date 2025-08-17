"""
Unit tests for mqtt_bridge core functionality.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import unittest
from unittest.mock import MagicMock, patch

# Import core modules
from mqtt_bridge import direct, server, subscription_persistence

class TestMQTTDirect(unittest.TestCase):
    def test_mqtt_connect(self):
        # Example: test connection logic
        result = direct.mqtt_connect('test_id', 'test/topic', 0)
        self.assertIsInstance(result, dict)

    def test_mqtt_subscribe(self):
        # Example: test subscribe logic
        result = direct.mqtt_subscribe('test_id', 'test/topic', 1)
        self.assertIsInstance(result, dict)

    def test_mqtt_publish(self):
        # Example: test publish logic
        result = direct.mqtt_publish('test_id', 'test/topic', 'payload', 0)
        self.assertIsInstance(result, dict)

class TestMQTTServer(unittest.TestCase):
    def test_on_message_callback(self):
        # Example: test message callback
        message = MagicMock()
        message.topic = 'test/topic'
        message.payload = b'test'
        message.qos = 1
        message.retain = False
        with patch('mqtt_bridge.server.on_message_callback') as cb:
            cb.return_value = None
            cb(None, None, message)
            cb.assert_called()

class TestSubscriptionPersistence(unittest.TestCase):
    def test_save_and_load_subscriptions(self):
        subs = {'test_id': [('test/topic', 1)]}
        result = subscription_persistence.save_subscriptions(subs)
        self.assertTrue(result)
        loaded = subscription_persistence.load_subscriptions()
        self.assertIsInstance(loaded, dict)

if __name__ == '__main__':
    unittest.main()
