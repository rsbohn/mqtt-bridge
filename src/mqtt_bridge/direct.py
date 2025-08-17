"""
Direct access module for MQTT functionality.
This module allows Claude to call MQTT functions directly without going through the MCP server protocol.
"""

import os
import platform
import json
import logging
import asyncio
from typing import Dict, List, Optional, Union, Any
from datetime import datetime

# Import MQTT libraries
import paho.mqtt.client as mqtt
import aiomqtt

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Store MQTT connections and subscriptions
mqtt_connections: Dict[str, dict] = {}
mqtt_subscriptions: Dict[str, List[str]] = {}
received_messages: List[dict] = []


def on_message_callback(client, userdata, message, properties=None):
    """Callback for when a message is received from MQTT broker."""
    try:
        payload = message.payload.decode("utf-8", errors="ignore")
        msg_data = {
            "topic": message.topic,
            "payload": payload,
            "qos": message.qos,
            "retain": message.retain,
            "timestamp": datetime.now().isoformat(),
            "connection_id": (
                userdata.get("connection_id", "unknown") if userdata else "unknown"
            ),
            "direction": "incoming",
        }
        received_messages.append(msg_data)
        logger.info(f"Received message on topic {message.topic}: {payload[:100]}")
    except Exception as e:
        logger.error(f"Error processing received message: {e}")


def mqtt_connect(
    connection_id: str,
    broker: str,
    port: int = 1883,
    username: Optional[str] = None,
    password: Optional[str] = None,
    client_id: Optional[str] = None,
    keep_alive: int = 60,
) -> dict:
    """
    Connect to an MQTT broker directly.

    Args:
        connection_id: Unique identifier for this connection
        broker: MQTT broker hostname or IP address
        port: MQTT broker port (default: 1883)
        username: MQTT username (optional)
        password: MQTT password (optional)
        client_id: MQTT client ID (optional, auto-generated if not provided)
        keep_alive: Keep alive interval in seconds (default: 60)

    Returns:
        dict: Connection result information
    """
    # Create MQTT client
    if not client_id:
        client_id = f"mcp-mqtt-direct-{connection_id}"

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        userdata={"connection_id": connection_id},
        protocol=mqtt.MQTTv5,
    )

    if username and password:
        client.username_pw_set(username, password)

    client.on_message = on_message_callback

    # Connect to broker
    try:
        client.connect(broker, port, keep_alive)
        client.loop_start()

        # Store connection info
        mqtt_connections[connection_id] = {
            "broker": broker,
            "port": port,
            "client_id": client_id,
            "connected": True,
            "client": client,
            "connect_time": datetime.now().timestamp(),
            "connected_at": datetime.now().isoformat(),
            "last_activity": datetime.now().timestamp(),
            "subscriptions": {},
        }
        mqtt_subscriptions[connection_id] = []

        return {
            "success": True,
            "message": f"Successfully connected to MQTT broker {broker}:{port} with connection ID '{connection_id}'",
            "connection_id": connection_id,
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to connect to MQTT broker {broker}:{port}: {str(e)}",
            "error": str(e),
        }


def mqtt_disconnect(connection_id: str) -> dict:
    """
    Disconnect from an MQTT broker.

    Args:
        connection_id: Connection ID to disconnect

    Returns:
        dict: Disconnection result information
    """
    if connection_id not in mqtt_connections:
        return {"success": False, "message": f"Connection '{connection_id}' not found"}

    client = mqtt_connections[connection_id]["client"]
    client.loop_stop()
    client.disconnect()

    mqtt_connections[connection_id]["connected"] = False
    mqtt_connections[connection_id]["disconnected_at"] = datetime.now().isoformat()

    return {
        "success": True,
        "message": f"Disconnected from MQTT broker for connection '{connection_id}'",
    }


def mqtt_publish(
    connection_id: str, topic: str, payload: str, qos: int = 0, retain: bool = False
) -> dict:
    """
    Publish a message to an MQTT topic.

    Args:
        connection_id: Connection ID to use for publishing
        topic: MQTT topic to publish to
        payload: Message payload to publish
        qos: Quality of Service level (0, 1, or 2)
        retain: Whether to retain the message

    Returns:
        dict: Publication result information
    """
    if connection_id not in mqtt_connections:
        return {"success": False, "message": f"Connection '{connection_id}' not found"}

    if not mqtt_connections[connection_id]["connected"]:
        return {
            "success": False,
            "message": f"Connection '{connection_id}' is not connected",
        }

    client = mqtt_connections[connection_id]["client"]
    result = client.publish(topic, payload, qos=qos, retain=retain)

    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        # Log the outgoing message
        msg_data = {
            "topic": topic,
            "payload": payload,
            "qos": qos,
            "retain": retain,
            "timestamp": datetime.now().isoformat(),
            "connection_id": connection_id,
            "direction": "outgoing",
        }
        received_messages.append(msg_data)

        return {
            "success": True,
            "message": f"Successfully published message to topic '{topic}' (QoS: {qos}, Retain: {retain})",
        }
    else:
        return {
            "success": False,
            "message": f"Failed to publish message to topic '{topic}': {mqtt.error_string(result.rc)}",
            "error": mqtt.error_string(result.rc),
        }


def mqtt_subscribe(connection_id: str, topic: str, qos: int = 0) -> dict:
    """
    Subscribe to an MQTT topic.

    Args:
        connection_id: Connection ID to use for subscription
        topic: MQTT topic to subscribe to (supports wildcards + and #)
        qos: Quality of Service level (0, 1, or 2)

    Returns:
        dict: Subscription result information
    """
    if connection_id not in mqtt_connections:
        return {"success": False, "message": f"Connection '{connection_id}' not found"}

    if not mqtt_connections[connection_id]["connected"]:
        return {
            "success": False,
            "message": f"Connection '{connection_id}' is not connected",
        }

    client = mqtt_connections[connection_id]["client"]
    result, mid = client.subscribe(topic, qos=qos)

    if result == mqtt.MQTT_ERR_SUCCESS:
        # Update the last activity timestamp
        mqtt_connections[connection_id]["last_activity"] = datetime.now().timestamp()

        # Add the subscription with its QoS level
        mqtt_connections[connection_id]["subscriptions"][topic] = qos
        mqtt_subscriptions[connection_id].append(topic)

        return {
            "success": True,
            "message": f"Successfully subscribed to topic '{topic}' with QoS {qos}",
        }
    else:
        return {
            "success": False,
            "message": f"Failed to subscribe to topic '{topic}': {mqtt.error_string(result)}",
            "error": mqtt.error_string(result),
        }


def mqtt_unsubscribe(connection_id: str, topic: str) -> dict:
    """
    Unsubscribe from an MQTT topic.

    Args:
        connection_id: Connection ID to use for unsubscription
        topic: MQTT topic to unsubscribe from

    Returns:
        dict: Unsubscription result information
    """
    if connection_id not in mqtt_connections:
        return {"success": False, "message": f"Connection '{connection_id}' not found"}

    if not mqtt_connections[connection_id]["connected"]:
        return {
            "success": False,
            "message": f"Connection '{connection_id}' is not connected",
        }

    client = mqtt_connections[connection_id]["client"]
    result, mid = client.unsubscribe(topic)

    if result == mqtt.MQTT_ERR_SUCCESS:
        # Update the last activity timestamp
        mqtt_connections[connection_id]["last_activity"] = datetime.now().timestamp()

        # Remove from subscriptions
        if topic in mqtt_connections[connection_id]["subscriptions"]:
            del mqtt_connections[connection_id]["subscriptions"][topic]
        if topic in mqtt_subscriptions[connection_id]:
            mqtt_subscriptions[connection_id].remove(topic)

        return {
            "success": True,
            "message": f"Successfully unsubscribed from topic '{topic}'",
        }
    else:
        return {
            "success": False,
            "message": f"Failed to unsubscribe from topic '{topic}': {mqtt.error_string(result)}",
            "error": mqtt.error_string(result),
        }


def mqtt_list_connections() -> dict:
    """
    List all MQTT connections and their status.

    Returns:
        dict: Information about all connections
    """
    if not mqtt_connections:
        return {
            "success": True,
            "message": "No MQTT connections found",
            "connections": [],
        }

    connections_list = []
    for conn_id, conn_info in mqtt_connections.items():
        # Filter out the client object which can't be serialized
        conn_data = {k: v for k, v in conn_info.items() if k != "client"}
        connections_list.append(conn_data)

    return {
        "success": True,
        "message": f"Found {len(connections_list)} MQTT connections",
        "connections": connections_list,
    }


def mqtt_get_messages(topic_filter: str = "", limit: int = 20) -> dict:
    """
    Get recent MQTT messages.

    Args:
        topic_filter: Filter messages by topic pattern (optional)
        limit: Maximum number of messages to return (default: 20)

    Returns:
        dict: Recent messages matching the filter
    """
    if not received_messages:
        return {
            "success": True,
            "message": "No MQTT messages received yet",
            "messages": [],
        }

    # Filter messages by topic if specified
    filtered_messages = []
    for msg in received_messages[-100:]:  # Last 100 messages
        if topic_filter and topic_filter not in msg.get("topic", ""):
            continue
        filtered_messages.append(msg)

    # Limit results
    recent_messages = filtered_messages[-limit:] if filtered_messages else []

    filter_text = f" matching '{topic_filter}'" if topic_filter else ""
    return {
        "success": True,
        "message": f"Found {len(recent_messages)} MQTT messages{filter_text}",
        "messages": recent_messages,
    }


def mqtt_get_persistent_subscriptions(connection_id: Optional[str] = None) -> dict:
    """
    Get list of persistent subscriptions.

    Args:
        connection_id: Optional connection ID to filter by

    Returns:
        dict: Information about persistent subscriptions
    """
    try:
        # Import here to avoid circular imports
        from mqtt_bridge.subscription_persistence import get_persistent_subscriptions

        # Get the subscriptions
        persistent_subs = get_persistent_subscriptions(connection_id)

        if not persistent_subs:
            filter_text = f" for connection '{connection_id}'" if connection_id else ""
            return {
                "success": True,
                "message": f"No persistent subscriptions found{filter_text}",
                "subscriptions": {},
            }

        # Format the results for display
        results = []
        for conn_id, subscriptions in persistent_subs.items():
            conn_info = f"Connection: {conn_id}"
            sub_list = []
            for sub in subscriptions:
                sub_list.append(f"  • Topic: {sub['topic']}, QoS: {sub['qos']}")
            results.append(conn_info + "\n" + "\n".join(sub_list))

        filter_text = f" for connection '{connection_id}'" if connection_id else ""

        return {
            "success": True,
            "message": f"Persistent Subscriptions{filter_text}:\n\n"
            + "\n\n".join(results),
            "subscriptions": persistent_subs,
        }
    except Exception as e:
        logger.error(f"Error getting persistent subscriptions: {e}")
        return {
            "success": False,
            "message": f"Error getting persistent subscriptions: {str(e)}",
            "error": str(e),
        }


def mqtt_delete_subscription(topic: str, connection_id: Optional[str] = None) -> dict:
    """
    Delete a specific subscription from persistence.

    Args:
        topic: The topic name to delete from persistence
        connection_id: Optional connection ID to restrict deletion to a specific connection

    Returns:
        dict: Result of the deletion operation
    """
    try:
        # Import here to avoid circular imports
        from mqtt_bridge.subscription_persistence import delete_subscription

        # Delete the subscription
        result = delete_subscription(topic, connection_id)

        # Update runtime tracking for active connections
        if result["deleted_count"] > 0:
            for conn_id in result["affected_connections"]:
                # Remove from subscriptions list if connection is active
                if conn_id in mqtt_connections:
                    subscriptions = mqtt_connections[conn_id].get("subscriptions", {})
                    if topic in subscriptions:
                        del subscriptions[topic]

                    # Update runtime tracking
                    if (
                        conn_id in mqtt_subscriptions
                        and topic in mqtt_subscriptions[conn_id]
                    ):
                        mqtt_subscriptions[conn_id].remove(topic)

        return {
            "success": True,
            "message": result["message"],
            "deleted_count": result["deleted_count"],
            "affected_connections": result["affected_connections"],
        }
    except Exception as e:
        logger.error(f"Error deleting subscription: {e}")
        return {
            "success": False,
            "message": f"Error deleting subscription: {str(e)}",
            "error": str(e),
        }


def mqtt_delete_all_subscriptions(confirm: bool = False) -> dict:
    """
    Delete all persistent subscriptions (nuclear option).

    Args:
        confirm: Confirmation to proceed with deletion

    Returns:
        dict: Result of the deletion operation
    """
    if not confirm:
        return {
            "success": False,
            "message": "Operation cancelled. To delete all subscriptions, set confirm=True.",
        }

    try:
        # Import here to avoid circular imports
        from mqtt_bridge.subscription_persistence import delete_all_subscriptions

        # Delete all subscriptions
        result = delete_all_subscriptions()

        # Clear runtime tracking for active connections
        if result["deleted_count"] > 0:
            # Clear all subscription records in active connections
            for conn_id in mqtt_connections:
                mqtt_connections[conn_id]["subscriptions"] = {}

            # Clear runtime tracking
            for conn_id in mqtt_subscriptions:
                mqtt_subscriptions[conn_id] = []

        return {
            "success": True,
            "message": result["message"],
            "deleted_count": result["deleted_count"],
            "affected_connections": result["affected_connections"],
        }
    except Exception as e:
        logger.error(f"Error deleting all subscriptions: {e}")
        return {
            "success": False,
            "message": f"Error deleting all subscriptions: {str(e)}",
            "error": str(e),
        }




# Clean up function that should be called when the application exits
def cleanup():
    """Clean up all MQTT connections."""
    for conn_id in list(mqtt_connections.keys()):
        try:
            if mqtt_connections[conn_id]["connected"]:
                client = mqtt_connections[conn_id]["client"]
                client.loop_stop()
                client.disconnect()
                logger.info(f"Disconnected MQTT connection: {conn_id}")
        except Exception as e:
            logger.error(f"Error disconnecting MQTT connection {conn_id}: {e}")


if __name__ == "__main__":
    print("*** MQTT Direct Access Module ***")
    print("This module is not intended to be run directly.")