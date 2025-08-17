import asyncio
import json
import logging
import os
import platform
import signal
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio

# Import MQTT libraries
import paho.mqtt.client as mqtt
import aiomqtt

# Import subscription persistence
from mqtt_bridge.subscription_persistence import save_subscriptions, load_subscriptions

# Setup logging to stderr (important for MCP servers)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Store MQTT connections and subscriptions
mqtt_connections: Dict[str, dict] = {}
mqtt_subscriptions: Dict[str, List[str]] = (
    {}
)  # Simple topic list (for backward compatibility)
mqtt_subscriptions_with_qos: Dict[str, List[Tuple[str, int]]] = (
    {}
)  # List of (topic, qos) tuples
received_messages: List[dict] = []

# Flag to track if we've already restored subscriptions
subscriptions_restored = False

server = Server("mcp-mqtt")


@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """
    List available MQTT resources.
    Each connection and recent messages are exposed as resources.
    """
    resources = []

    # Add connection status resources
    for conn_id, conn_info in mqtt_connections.items():
        resources.append(
            types.Resource(
                uri=AnyUrl(f"mqtt://connection/{conn_id}"),
                name=f"MQTT Connection: {conn_id}",
                description=f"Status and details for MQTT connection {conn_id}",
                mimeType="application/json",
            )
        )

    # Add recent messages resource
    resources.append(
        types.Resource(
            uri=AnyUrl("mqtt://messages/recent"),
            name="Recent MQTT Messages",
            description="List of recently received MQTT messages",
            mimeType="application/json",
        )
    )
    
    return resources


@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    """
    Read MQTT resource content.
    """
    if uri.scheme != "mqtt":
        raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

    path = uri.path
    if path is not None:
        path = path.lstrip("/")
        if path.startswith("connection/"):
            conn_id = path.split("/", 1)[1]
            if conn_id in mqtt_connections:
                return json.dumps(mqtt_connections[conn_id], indent=2)
            else:
                raise ValueError(f"Connection not found: {conn_id}")
        elif path == "messages/recent":
            return json.dumps(received_messages[-100:], indent=2)  # Last 100 messages
    raise ValueError(f"Resource not found: {path}")


@server.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]:
    """
    List available MQTT prompts.
    """
    return [
        types.Prompt(
            name="mqtt-connection-status",
            description="Get status of all MQTT connections",
            arguments=[
                types.PromptArgument(
                    name="format",
                    description="Output format (summary/detailed)",
                    required=False,
                )
            ],
        ),
        types.Prompt(
            name="mqtt-message-analysis",
            description="Analyze recent MQTT messages",
            arguments=[
                types.PromptArgument(
                    name="topic_filter",
                    description="Filter messages by topic pattern",
                    required=False,
                ),
                types.PromptArgument(
                    name="time_window",
                    description="Time window in minutes (default: 60)",
                    required=False,
                ),
            ],
        ),
    ]


@server.get_prompt()
async def handle_get_prompt(
    name: str, arguments: dict[str, str] | None
) -> types.GetPromptResult:
    """
    Generate MQTT-related prompts.
    """
    if name == "mqtt-connection-status":
        format_type = (arguments or {}).get("format", "summary")
        detail_prompt = (
            " Include detailed connection parameters and statistics."
            if format_type == "detailed"
            else ""
        )

        connections_info = []
        for conn_id, conn_info in mqtt_connections.items():
            status = (
                "Connected" if conn_info.get("connected", False) else "Disconnected"
            )
            connections_info.append(
                f"- {conn_id}: {status} ({conn_info.get('broker', 'unknown broker')})"
            )

        return types.GetPromptResult(
            description="MQTT connection status summary",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=(
                            f"Current MQTT connections:{detail_prompt}\n\n"
                            + "\n".join(connections_info)
                            if connections_info
                            else "No active connections"
                        ),
                    ),
                )
            ],
        )

    elif name == "mqtt-message-analysis":
        topic_filter = (arguments or {}).get("topic_filter", "")
        time_window = int((arguments or {}).get("time_window", "60"))

        # Filter messages by topic and time
        filtered_messages = []
        for msg in received_messages[-100:]:  # Last 100 messages
            if topic_filter and topic_filter not in msg.get("topic", ""):
                continue
            filtered_messages.append(
                f"Topic: {msg.get('topic', 'unknown')}, Payload: {msg.get('payload', '')[:100]}"
            )

        return types.GetPromptResult(
            description="Recent MQTT message analysis",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=(
                            f"Recent MQTT messages (last {time_window} minutes):\n\n"
                            + "\n".join(filtered_messages[-20:])
                            if filtered_messages
                            else "No messages received"
                        ),
                    ),
                )
            ],
        )

    raise ValueError(f"Unknown prompt: {name}")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available MQTT tools.
    """
    return [
        types.Tool(
            name="mqtt-connect",
            description="Connect to an MQTT broker",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection_id": {
                        "type": "string",
                        "description": "Unique identifier for this connection",
                    },
                    "broker": {
                        "type": "string",
                        "description": "MQTT broker hostname or IP address",
                    },
                    "port": {
                        "type": "integer",
                        "description": "MQTT broker port (default: 1883)",
                        "default": 1883,
                    },
                    "username": {
                        "type": "string",
                        "description": "MQTT username (optional)",
                    },
                    "password": {
                        "type": "string",
                        "description": "MQTT password (optional)",
                    },
                    "client_id": {
                        "type": "string",
                        "description": "MQTT client ID (optional, auto-generated if not provided)",
                    },
                    "keep_alive": {
                        "type": "integer",
                        "description": "Keep alive interval in seconds (default: 60)",
                        "default": 60,
                    },
                },
                "required": ["connection_id", "broker"],
            },
        ),
        types.Tool(
            name="mqtt-disconnect",
            description="Disconnect from an MQTT broker",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection_id": {
                        "type": "string",
                        "description": "Connection ID to disconnect",
                    }
                },
                "required": ["connection_id"],
            },
        ),
        types.Tool(
            name="mqtt-publish",
            description="Publish a message to an MQTT topic",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection_id": {
                        "type": "string",
                        "description": "Connection ID to use for publishing",
                    },
                    "topic": {
                        "type": "string",
                        "description": "MQTT topic to publish to",
                    },
                    "payload": {
                        "type": "string",
                        "description": "Message payload to publish",
                    },
                    "qos": {
                        "type": "integer",
                        "description": "Quality of Service level (0, 1, or 2)",
                        "enum": [0, 1, 2],
                        "default": 0,
                    },
                    "retain": {
                        "type": "boolean",
                        "description": "Whether to retain the message",
                        "default": False,
                    },
                },
                "required": ["connection_id", "topic", "payload"],
            },
        ),
        types.Tool(
            name="mqtt-subscribe",
            description="Subscribe to an MQTT topic",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection_id": {
                        "type": "string",
                        "description": "Connection ID to use for subscription",
                    },
                    "topic": {
                        "type": "string",
                        "description": "MQTT topic to subscribe to (supports wildcards + and #)",
                    },
                    "qos": {
                        "type": "integer",
                        "description": "Quality of Service level (0, 1, or 2)",
                        "enum": [0, 1, 2],
                        "default": 0,
                    },
                },
                "required": ["connection_id", "topic"],
            },
        ),
        types.Tool(
            name="mqtt-unsubscribe",
            description="Unsubscribe from an MQTT topic",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection_id": {
                        "type": "string",
                        "description": "Connection ID to use for unsubscription",
                    },
                    "topic": {
                        "type": "string",
                        "description": "MQTT topic to unsubscribe from",
                    },
                },
                "required": ["connection_id", "topic"],
            },
        ),
        types.Tool(
            name="mqtt-list-connections",
            description="List all MQTT connections and their status",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="mqtt-get-messages",
            description="Get recent MQTT messages",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic_filter": {
                        "type": "string",
                        "description": "Filter messages by topic pattern (optional)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of messages to return (default: 20)",
                        "default": 20,
                    },
                },
            },
        ),
        types.Tool(
            name="mqtt-get-persistent-subscriptions",
            description="Get list of persistent subscriptions",
            inputSchema={
                "type": "object",
                "properties": {
                    "connection_id": {
                        "type": "string",
                        "description": "Filter subscriptions by connection ID (optional)",
                    }
                },
            },
        ),
        types.Tool(
            name="mqtt-delete-subscription",
            description="Delete a specific subscription from persistence",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The topic name to delete from persistence",
                    },
                    "connection_id": {
                        "type": "string",
                        "description": "Connection ID to restrict deletion to (optional). If not provided, removes from all connections.",
                    },
                },
                "required": ["topic"],
            },
        ),
        types.Tool(
            name="mqtt-delete-all-subscriptions",
            description="Delete all persistent subscriptions (nuclear option)",
            inputSchema={
                "type": "object",
                "properties": {
                    "confirm": {
                        "type": "boolean",
                        "description": "Confirmation that you want to delete all subscriptions",
                        "default": False,
                    }
                },
                "required": ["confirm"],
            },
        ),
    ]


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
        }
        received_messages.append(msg_data)
        logger.info(f"Received message on topic {message.topic}: {payload[:100]}")
    except Exception as e:
        logger.error(f"Error processing received message: {e}")


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle MQTT tool execution requests.
    """
    if not arguments:
        arguments = {}

    # SECURITY: Don't accept credentials from the client. Use stored credentials instead.
    try:
        if name == "mqtt-connect":
            connection_id = arguments["connection_id"]
            broker = arguments["broker"]
            port = arguments.get("port", 1883)
            username = arguments.get("username")
            password = arguments.get("password")
            client_id = arguments.get("client_id", f"mcp-mqtt-{connection_id}")
            keep_alive = arguments.get("keep_alive", 60)

            # Create MQTT client
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
                    "connected_at": datetime.now().isoformat(),
                    "subscriptions": [],
                }
                mqtt_subscriptions[connection_id] = []

                # Restore any saved subscriptions for this connection
                if connection_id in mqtt_subscriptions_with_qos:
                    restored_count = 0
                    for topic, qos in mqtt_subscriptions_with_qos[connection_id]:
                        try:
                            result, _ = client.subscribe(topic, qos)
                            if result == mqtt.MQTT_ERR_SUCCESS:
                                mqtt_connections[connection_id]["subscriptions"].append(
                                    topic
                                )
                                mqtt_subscriptions[connection_id].append(topic)
                                restored_count += 1
                            else:
                                logger.warning(
                                    f"Failed to restore subscription to '{topic}': {mqtt.error_string(result)}"
                                )
                        except Exception as e:
                            logger.error(
                                f"Error restoring subscription to '{topic}': {e}"
                            )

                    if restored_count > 0:
                        logger.info(
                            f"Restored {restored_count} subscriptions for connection {connection_id}"
                        )

                await server.request_context.session.send_resource_list_changed()

                return [
                    types.TextContent(
                        type="text",
                        text=f"Successfully connected to MQTT broker {broker}:{port} with connection ID '{connection_id}'",
                    )
                ]
            except Exception as e:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Failed to connect to MQTT broker {broker}:{port}: {str(e)}",
                    )
                ]

        elif name == "mqtt-disconnect":
            connection_id = arguments["connection_id"]

            if connection_id not in mqtt_connections:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Connection '{connection_id}' not found",
                    )
                ]

            client = mqtt_connections[connection_id]["client"]
            client.loop_stop()
            client.disconnect()

            mqtt_connections[connection_id]["connected"] = False
            mqtt_connections[connection_id][
                "disconnected_at"
            ] = datetime.now().isoformat()

            await server.request_context.session.send_resource_list_changed()

            return [
                types.TextContent(
                    type="text",
                    text=f"Disconnected from MQTT broker for connection '{connection_id}'",
                )
            ]

        elif name == "mqtt-publish":
            connection_id = arguments["connection_id"]
            topic = arguments["topic"]
            payload = arguments["payload"]
            qos = arguments.get("qos", 0)
            retain = arguments.get("retain", False)

            if connection_id not in mqtt_connections:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Connection '{connection_id}' not found",
                    )
                ]

            if not mqtt_connections[connection_id]["connected"]:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Connection '{connection_id}' is not connected",
                    )
                ]

            client = mqtt_connections[connection_id]["client"]
            result = client.publish(topic, payload, qos=qos, retain=retain)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Successfully published message to topic '{topic}' (QoS: {qos}, Retain: {retain})",
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Failed to publish message to topic '{topic}': {mqtt.error_string(result.rc)}",
                    )
                ]

        elif name == "mqtt-subscribe":
            connection_id = arguments["connection_id"]
            topic = arguments["topic"]
            qos = arguments.get("qos", 0)

            if connection_id not in mqtt_connections:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Connection '{connection_id}' not found",
                    )
                ]

            if not mqtt_connections[connection_id]["connected"]:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Connection '{connection_id}' is not connected",
                    )
                ]

            client = mqtt_connections[connection_id]["client"]
            result, mid = client.subscribe(topic, qos=qos)

            if result == mqtt.MQTT_ERR_SUCCESS:
                # Track subscription in legacy format (just topics)
                mqtt_connections[connection_id]["subscriptions"].append(topic)
                mqtt_subscriptions[connection_id].append(topic)

                # Track subscription with QoS
                if connection_id not in mqtt_subscriptions_with_qos:
                    mqtt_subscriptions_with_qos[connection_id] = []
                mqtt_subscriptions_with_qos[connection_id].append((topic, qos))

                # Save subscriptions to disk for persistence
                save_subscriptions(mqtt_subscriptions_with_qos)

                return [
                    types.TextContent(
                        type="text",
                        text=f"Successfully subscribed to topic '{topic}' with QoS {qos}",
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Failed to subscribe to topic '{topic}': {mqtt.error_string(result)}",
                    )
                ]

        elif name == "mqtt-unsubscribe":
            connection_id = arguments["connection_id"]
            topic = arguments["topic"]

            if connection_id not in mqtt_connections:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Connection '{connection_id}' not found",
                    )
                ]

            if not mqtt_connections[connection_id]["connected"]:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Connection '{connection_id}' is not connected",
                    )
                ]

            client = mqtt_connections[connection_id]["client"]
            result, mid = client.unsubscribe(topic)

            if result == mqtt.MQTT_ERR_SUCCESS:
                # Remove from legacy tracking
                if topic in mqtt_connections[connection_id]["subscriptions"]:
                    mqtt_connections[connection_id]["subscriptions"].remove(topic)
                if topic in mqtt_subscriptions[connection_id]:
                    mqtt_subscriptions[connection_id].remove(topic)

                # Remove from QoS tracking (find by topic name)
                if connection_id in mqtt_subscriptions_with_qos:
                    mqtt_subscriptions_with_qos[connection_id] = [
                        (t, q)
                        for t, q in mqtt_subscriptions_with_qos[connection_id]
                        if t != topic
                    ]

                    # If the connection has no more subscriptions, remove it from tracking
                    if not mqtt_subscriptions_with_qos[connection_id]:
                        del mqtt_subscriptions_with_qos[connection_id]

                # Save updated subscriptions to disk
                save_subscriptions(mqtt_subscriptions_with_qos)

                return [
                    types.TextContent(
                        type="text",
                        text=f"Successfully unsubscribed from topic '{topic}'",
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Failed to unsubscribe from topic '{topic}': {mqtt.error_string(result)}",
                    )
                ]

        elif name == "mqtt-list-connections":
            if not mqtt_connections:
                return [
                    types.TextContent(
                        type="text",
                        text="No MQTT connections found",
                    )
                ]

            connection_list = []
            for conn_id, conn_info in mqtt_connections.items():
                status = (
                    "Connected" if conn_info.get("connected", False) else "Disconnected"
                )
                subscriptions = conn_info.get("subscriptions", [])
                connection_list.append(
                    f"ID: {conn_id}\n"
                    f"  Broker: {conn_info.get('broker', 'unknown')}:{conn_info.get('port', 'unknown')}\n"
                    f"  Status: {status}\n"
                    f"  Client ID: {conn_info.get('client_id', 'unknown')}\n"
                    f"  Connected at: {conn_info.get('connected_at', 'unknown')}\n"
                    f"  Subscriptions: {', '.join(subscriptions) if subscriptions else 'None'}\n"
                )

            return [
                types.TextContent(
                    type="text",
                    text="MQTT Connections:\n\n" + "\n".join(connection_list),
                )
            ]

        elif name == "mqtt-get-messages":
            topic_filter = arguments.get("topic_filter", "")
            limit = arguments.get("limit", 20)

            if not received_messages:
                return [
                    types.TextContent(
                        type="text",
                        text="No MQTT messages received yet",
                    )
                ]

            # Filter messages by topic if specified
            filtered_messages = []
            for msg in received_messages[-100:]:  # Last 100 messages
                if topic_filter and topic_filter not in msg.get("topic", ""):
                    continue
                filtered_messages.append(msg)

            # Limit results
            recent_messages = filtered_messages[-limit:] if filtered_messages else []

            if not recent_messages:
                filter_text = f" matching '{topic_filter}'" if topic_filter else ""
                return [
                    types.TextContent(
                        type="text",
                        text=f"No MQTT messages found{filter_text}",
                    )
                ]

            message_list = []
            for msg in recent_messages:
                message_list.append(
                    f"Topic: {msg.get('topic', 'unknown')}\n"
                    f"  Payload: {msg.get('payload', '')}\n"
                    f"  QoS: {msg.get('qos', 0)}\n"
                    f"  Retain: {msg.get('retain', False)}\n"
                    f"  Timestamp: {msg.get('timestamp', 'unknown')}\n"
                    f"  Connection: {msg.get('connection_id', 'unknown')}\n"
                )

            filter_text = f" (filtered by '{topic_filter}')" if topic_filter else ""
            return [
                types.TextContent(
                    type="text",
                    text=f"Recent MQTT Messages{filter_text}:\n\n"
                    + "\n".join(message_list),
                )
            ]

        elif name == "mqtt-get-persistent-subscriptions":
            connection_id = arguments.get("connection_id")

            # Get persistent subscriptions
            from mqtt_bridge.subscription_persistence import get_persistent_subscriptions

            persistent_subs = get_persistent_subscriptions(connection_id)

            if not persistent_subs:
                filter_text = (
                    f" for connection '{connection_id}'" if connection_id else ""
                )
                return [
                    types.TextContent(
                        type="text",
                        text=f"No persistent subscriptions found{filter_text}",
                    )
                ]

            # Format the results
            results = []
            for conn_id, subscriptions in persistent_subs.items():
                conn_info = f"Connection: {conn_id}\n"
                sub_list = []
                for sub in subscriptions:
                    sub_list.append(f"  • Topic: {sub['topic']}, QoS: {sub['qos']}")
                results.append(conn_info + "\n".join(sub_list))

            filter_text = f" for connection '{connection_id}'" if connection_id else ""
            return [
                types.TextContent(
                    type="text",
                    text=f"Persistent Subscriptions{filter_text}:\n\n"
                    + "\n\n".join(results),
                )
            ]

        elif name == "mqtt-delete-subscription":
            topic = arguments["topic"]
            connection_id = arguments.get("connection_id")

            # Import the deletion function
            from mqtt_bridge.subscription_persistence import delete_subscription

            # Perform the deletion
            result = delete_subscription(topic, connection_id)

            if result["success"]:
                # Update our runtime tracking if any were deleted
                if result["deleted_count"] > 0:
                    for conn_id in result["affected_connections"]:
                        # Remove from runtime tracking if the connection exists
                        if conn_id in mqtt_subscriptions_with_qos:
                            mqtt_subscriptions_with_qos[conn_id] = [
                                (t, q)
                                for t, q in mqtt_subscriptions_with_qos[conn_id]
                                if t != topic
                            ]
                            # If no subscriptions left, remove the connection
                            if not mqtt_subscriptions_with_qos[conn_id]:
                                del mqtt_subscriptions_with_qos[conn_id]

                        # Update legacy tracking
                        if conn_id in mqtt_subscriptions:
                            if topic in mqtt_subscriptions[conn_id]:
                                mqtt_subscriptions[conn_id].remove(topic)

                        # Update connection info if connection is active
                        if conn_id in mqtt_connections:
                            if topic in mqtt_connections[conn_id]["subscriptions"]:
                                mqtt_connections[conn_id]["subscriptions"].remove(topic)

                return [
                    types.TextContent(
                        type="text",
                        text=result["message"],
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Error deleting subscription: {result.get('error', 'Unknown error')}",
                    )
                ]

        elif name == "mqtt-delete-all-subscriptions":
            confirm = arguments.get("confirm", False)

            if not confirm:
                return [
                    types.TextContent(
                        type="text",
                        text="Operation cancelled. To delete all subscriptions, set confirm=True.",
                    )
                ]

            # Import the deletion function
            from mqtt_bridge.subscription_persistence import delete_all_subscriptions

            # Perform the deletion
            result = delete_all_subscriptions()

            if result["success"]:
                # Clear runtime tracking as well
                mqtt_subscriptions_with_qos.clear()

                # Clear legacy subscription tracking
                for conn_id in mqtt_subscriptions:
                    mqtt_subscriptions[conn_id] = []

                # Clear subscription lists in active connections
                for conn_id, conn_info in mqtt_connections.items():
                    conn_info["subscriptions"] = []

                return [
                    types.TextContent(
                        type="text",
                        text=result["message"],
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Error deleting all subscriptions: {result.get('error', 'Unknown error')}",
                    )
                ]

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        logger.error(f"Error in tool '{name}': {e}")
        return [
            types.TextContent(
                type="text",
                text=f"Error executing tool '{name}': {str(e)}",
            )
        ]


async def main():
    """Main function to run the MCP MQTT server."""
    # Create a startup banner with file info
    server_file = __file__
    last_modified = datetime.fromtimestamp(os.path.getmtime(server_file)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    logger.info("Starting MCP MQTT Server...")
    logger.info(f"Server file: {server_file}")
    logger.info(f"Last modified: {last_modified}")
    # Log the full path to the log file if available
    handler = logger.handlers[0] if logger.handlers else None
    log_file_path = getattr(handler, "baseFilename", None)
    if log_file_path:
        logger.info(f"Full path to log file: {os.path.abspath(log_file_path)}")
    else:
        logger.info("Logging to stderr (no log file path available)")

    # Load saved subscriptions
    global mqtt_subscriptions_with_qos
    mqtt_subscriptions_with_qos = load_subscriptions()
    logger.info(
        f"Loaded subscription persistence data for {len(mqtt_subscriptions_with_qos)} connections"
    )

    # Setup signal handlers for graceful shutdown
    def handle_shutdown(sig, frame):
        logger.info(f"Received signal {sig}, saving subscriptions and shutting down...")
        save_subscriptions(mqtt_subscriptions_with_qos)

        # Disconnect all clients
        for conn_id, conn_info in mqtt_connections.items():
            try:
                if conn_info["connected"]:
                    client = conn_info["client"]
                    client.loop_stop()
                    client.disconnect()
                    logger.info(f"Disconnected client {conn_id}")
            except Exception as e:
                logger.error(f"Error disconnecting client {conn_id}: {e}")

    # Register signal handlers
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcp-mqtt",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":

    asyncio.run(main())
