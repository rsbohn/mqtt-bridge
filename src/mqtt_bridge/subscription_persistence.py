"""
Subscription persistence module for MCP-MQTT.

This module provides functionality to save and restore MQTT subscription
information across server restarts.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Setup module logging
logger = logging.getLogger(__name__)

# Default persistence directory and file
DEFAULT_PERSISTENCE_DIR = "~/.mqtt-bridge"
DEFAULT_SUBSCRIPTIONS_FILE = "subscriptions.json"


def get_persistence_path() -> Path:
    """
    Get the path to the subscription persistence file.

    Returns:
        Path: The path to the subscription persistence file.
    """
    # Get persistence directory from environment or use default
    persistence_dir = os.getenv("MQTT_BRIDGE_PERSISTENCE_DIR", DEFAULT_PERSISTENCE_DIR)
    persistence_dir = Path(persistence_dir).expanduser()

    # Get subscriptions file from environment or use default
    subscriptions_file = os.getenv(
        "MQTT_BRIDGE_SUBSCRIPTIONS_FILE", DEFAULT_SUBSCRIPTIONS_FILE
    )

    # Create the full path
    return persistence_dir / subscriptions_file


def ensure_persistence_directory() -> None:
    """
    Ensure the persistence directory exists.
    """
    persistence_path = get_persistence_path()
    persistence_path.parent.mkdir(parents=True, exist_ok=True)


def save_subscriptions(subscriptions: Dict[str, List[Tuple[str, int]]]) -> bool:
    """
    Save subscriptions to disk.

    Args:
        subscriptions: Dictionary mapping connection_id to list of (topic, qos) tuples

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Ensure the directory exists
        ensure_persistence_directory()

        # Convert the subscriptions dictionary to a serializable format
        # Format: {connection_id: [{"topic": topic, "qos": qos}, ...], ...}
        serializable_subscriptions = {}
        for conn_id, topic_list in subscriptions.items():
            serializable_subscriptions[conn_id] = [
                {"topic": topic, "qos": qos} for topic, qos in topic_list
            ]

        # Save to disk
        with open(get_persistence_path(), "w") as f:
            json.dump(serializable_subscriptions, f, indent=2)

        logger.info(
            f"Saved {sum(len(topics) for topics in subscriptions.values())} "
            f"subscriptions for {len(subscriptions)} connections to {get_persistence_path()}"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to save subscriptions: {e}")
        return False


def load_subscriptions() -> Dict[str, List[Tuple[str, int]]]:
    """
    Load subscriptions from disk.

    Returns:
        Dict[str, List[Tuple[str, int]]]: Dictionary mapping connection_id to list of (topic, qos) tuples
    """
    persistence_path = get_persistence_path()

    if not persistence_path.exists():
        logger.info(f"No subscription persistence file found at {persistence_path}")
        return {}

    try:
        with open(persistence_path, "r") as f:
            serialized_subscriptions = json.load(f)

        # Convert the serialized format back to the expected format
        subscriptions = {}
        for conn_id, topic_list in serialized_subscriptions.items():
            subscriptions[conn_id] = [
                (item["topic"], item["qos"]) for item in topic_list
            ]

        logger.info(
            f"Loaded {sum(len(topics) for topics in subscriptions.values())} "
            f"subscriptions for {len(subscriptions)} connections from {persistence_path}"
        )
        return subscriptions
    except Exception as e:
        logger.error(f"Failed to load subscriptions: {e}")
        return {}


def get_persistent_subscriptions(
    connection_id: Optional[str] = None,
) -> Dict[str, List[dict]]:
    """
    Get persistent subscriptions in a user-friendly format.

    Args:
        connection_id: Optional connection ID to filter by. If None, returns all subscriptions.

    Returns:
        Dict[str, List[dict]]: Dictionary mapping connection_id to list of subscription dictionaries.
                               Each subscription dictionary contains 'topic' and 'qos' keys.
    """
    # Load subscriptions from disk
    subscriptions = load_subscriptions()

    # If a specific connection ID is requested, filter the results
    if connection_id is not None:
        if connection_id in subscriptions:
            # Convert to user-friendly format
            return {
                connection_id: [
                    {"topic": topic, "qos": qos}
                    for topic, qos in subscriptions[connection_id]
                ]
            }
        else:
            return {}

    # Convert all subscriptions to user-friendly format
    result = {}
    for conn_id, topic_list in subscriptions.items():
        result[conn_id] = [{"topic": topic, "qos": qos} for topic, qos in topic_list]

    return result


def delete_subscription(
    topic_name: str, connection_id: Optional[str] = None
) -> Dict[str, object]:
    """
    Delete a specific subscription from persistence.

    Args:
        topic_name: The topic name to delete
        connection_id: Optional connection ID to restrict deletion to a specific connection.
                      If None, removes the topic from all connections.

    Returns:
        Dict with results: {
            "success": bool,
            "deleted_count": int,
            "affected_connections": List[str]
        }
    """
    # Load current subscriptions
    subscriptions = load_subscriptions()
    if not subscriptions:
        return {
            "success": True,
            "deleted_count": 0,
            "affected_connections": [],
            "message": "No subscriptions found to delete.",
        }

    deleted_count = 0
    affected_connections = []

    # If connection_id is specified, only look in that connection
    if connection_id is not None:
        if connection_id not in subscriptions:
            return {
                "success": True,
                "deleted_count": 0,
                "affected_connections": [],
                "message": f"Connection '{connection_id}' not found in persistence.",
            }

        # Count topics that will be removed
        original_count = len(subscriptions[connection_id])

        # Filter out the specified topic
        subscriptions[connection_id] = [
            (topic, qos)
            for topic, qos in subscriptions[connection_id]
            if topic != topic_name
        ]

        # Calculate how many were removed
        new_count = len(subscriptions[connection_id])
        deleted_count = original_count - new_count

        # If any were removed, mark this connection as affected
        if deleted_count > 0:
            affected_connections.append(connection_id)

        # If connection has no more subscriptions, remove it
        if new_count == 0:
            del subscriptions[connection_id]
    else:
        # Check all connections
        for conn_id in list(subscriptions.keys()):
            original_count = len(subscriptions[conn_id])

            # Filter out the specified topic
            subscriptions[conn_id] = [
                (topic, qos)
                for topic, qos in subscriptions[conn_id]
                if topic != topic_name
            ]

            # Calculate how many were removed
            new_count = len(subscriptions[conn_id])
            conn_deleted = original_count - new_count

            # If any were removed, update counts and affected list
            if conn_deleted > 0:
                deleted_count += conn_deleted
                affected_connections.append(conn_id)

            # If connection has no more subscriptions, remove it
            if new_count == 0:
                del subscriptions[conn_id]

    # Save the updated subscriptions
    if deleted_count > 0:
        save_subscriptions(subscriptions)

    return {
        "success": True,
        "deleted_count": deleted_count,
        "affected_connections": affected_connections,
        "message": f"Deleted {deleted_count} subscription(s) for topic '{topic_name}' from {len(affected_connections)} connection(s).",
    }


def delete_all_subscriptions() -> Dict[str, object]:
    """
    Delete all subscriptions from persistence (nuclear option).

    Returns:
        Dict with results: {
            "success": bool,
            "deleted_count": int,
            "affected_connections": List[str]
        }
    """
    # Load current subscriptions to get counts for reporting
    subscriptions = load_subscriptions()

    if not subscriptions:
        return {
            "success": True,
            "deleted_count": 0,
            "affected_connections": [],
            "message": "No subscriptions found to delete.",
        }

    # Calculate totals for reporting
    deleted_count = sum(len(topics) for topics in subscriptions.values())
    affected_connections = list(subscriptions.keys())

    # Create empty persistence file
    try:
        # Ensure the directory exists
        ensure_persistence_directory()

        # Save empty dictionary
        with open(get_persistence_path(), "w") as f:
            json.dump({}, f, indent=2)

        logger.info(
            f"Deleted all subscriptions ({deleted_count} total) for {len(affected_connections)} connections"
        )

        return {
            "success": True,
            "deleted_count": deleted_count,
            "affected_connections": affected_connections,
            "message": f"Deleted all subscriptions ({deleted_count} total) for {len(affected_connections)} connections.",
        }
    except Exception as e:
        logger.error(f"Failed to delete all subscriptions: {e}")
        return {
            "success": False,
            "deleted_count": 0,
            "affected_connections": [],
            "error": str(e),
            "message": f"Failed to delete all subscriptions: {e}",
        }
