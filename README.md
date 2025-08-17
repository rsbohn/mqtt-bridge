
# MQTT-Bridge

MQTT-Bridge provides MQTT communication capabilities for Large Language Models and other clients. It enables connections to MQTT brokers, publishing and subscribing to topics, and managing real-time messaging workflows.

## Features

- **MQTT Broker Connection**: Connect to any MQTT broker with authentication support
- **Message Publishing**: Publish messages to topics with configurable QoS and retain settings
- **Topic Subscription**: Subscribe to topics with wildcard support (+ and #)
- **Connection Management**: Manage multiple concurrent MQTT connections
- **Message Monitoring**: Track and analyze received messages
- **Real-time Updates**: Live message reception and connection status monitoring
- **Subscription Persistence**: Maintain subscriptions across server restarts


## Components

### Resources

MQTT-Bridge provides these resources:
- **Connection Status**: Real-time status and details for each MQTT connection
- **Message History**: Recent MQTT messages with filtering capabilities

### Prompts

MQTT-Bridge offers intelligent prompts for:
- **mqtt-connection-status**: Get formatted status of all MQTT connections
- **mqtt-message-analysis**: Analyze recent MQTT messages with topic filtering

### Tools

MQTT-Bridge implements these MQTT tools:

1. **mqtt-connect**: Connect to an MQTT broker
   - Supports authentication (username/password)
   - Configurable client ID, keep-alive, and port settings
   - Automatically restores saved subscriptions
   
2. **mqtt-disconnect**: Disconnect from an MQTT broker

3. **mqtt-publish**: Publish messages to topics
   - Configurable QoS levels (0, 1, 2)
   - Retain message support
   
4. **mqtt-subscribe**: Subscribe to topics
   - Wildcard support (+ for single level, # for multi-level)
   - Configurable QoS levels
   - Subscriptions are persisted automatically
   
5. **mqtt-unsubscribe**: Unsubscribe from topics
   - Automatically updates persistence storage

6. **mqtt-list-connections**: List all connections and their status

7. **mqtt-get-messages**: Retrieve recent messages with optional filtering

8. **mqtt-get-persistent-subscriptions**: Retrieve persisted subscription information
   - View all subscriptions across connections
   - Filter by connection ID
   - Shows topic and QoS information
   
9. **mqtt-delete-subscription**: Delete specific subscriptions from persistence
   - Delete from specific connection or all connections
   - Updates runtime tracking for active connections
   
10. **mqtt-delete-all-subscriptions**: Delete all persistent subscriptions
    - Nuclear option with confirmation required
    - Completely clears subscription persistence


## Installation

### Prerequisites

- Python 3.12 or higher
- uv package manager (recommended) or pip

### Setup

1. Clone or download this repository
2. Install dependencies:
   ```bash
   uv sync --dev --all-extras
   ```

Alternatively with pip:
```bash
pip install -e .
```

## Configuration


### Claude Desktop

Add this configuration to your Claude Desktop config file:

**MacOS**: `~/Library/Application\ Support/Claude/claude_desktop_config.json`  
**Windows**: `%APPDATA%/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "mqtt-bridge": {
      "command": "python",
      "args": ["-m", "mqtt_bridge.server"]
    }
  }
}
```


### Project Structure

```
src/
  mqtt_bridge/
    __init__.py
    server.py                    # Main server implementation
    subscription_persistence.py  # Subscription persistence implementation
.github/
  copilot-instructions.md        # GitHub Copilot workspace instructions
.vscode/
  mcp.json                       # VS Code MCP configuration
  tasks.json                     # Build and run tasks
```

## Subscription Persistence

The server implements subscription persistence to maintain MQTT subscriptions across server restarts:

### Features
- Automatically saves subscriptions to disk when they are created or removed
- Restores subscriptions when connections are re-established
- Preserves QoS levels for each subscription
- Gracefully handles shutdown to ensure latest subscription state is saved

### Configuration
Subscription persistence can be configured via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `MQTT_BRIDGE_PERSISTENCE_DIR` | Directory for persistence files | `~/.mqtt-bridge` |
| `MQTT_BRIDGE_SUBSCRIPTIONS_FILE` | Filename for subscriptions | `subscriptions.json` |

### Storage Format
Subscriptions are stored in a JSON file with the following structure:

```json
{
  "connection_id1": [
    {"topic": "topic1", "qos": 0},
    {"topic": "topic2", "qos": 1}
  ],
  "connection_id2": [
    {"topic": "topic3", "qos": 2}
  ]
}
```

### Testing
The `scripts/test_subscription_persistence.py` script can be used to test the subscription persistence functionality.

## Subscription Management

The server provides advanced subscription management capabilities:

### Viewing Subscriptions

Use the `mqtt-get-persistent-subscriptions` tool to view all persistent subscriptions:
```
Show me all persistent MQTT subscriptions
```

Filter by connection ID:
```
Show the persistent subscriptions for connection "my-connection"
```

### Deleting Subscriptions

Delete a specific subscription from all connections:
```
Delete subscription for topic "sensors/temperature"
```

Delete a subscription from a specific connection:
```
Delete the "sensors/temperature" subscription from connection "my-connection"
```

### Nuclear Option

Delete all persistent subscriptions (requires confirmation):
```
Delete all persistent subscriptions
```
pyproject.toml          # Project configuration
README.md               # This file
```

### Running the Server

For development:

```bash
uv run python -m mqtt_bridge.server
```

For production:
```bash
python -m mqtt_bridge.server
```

### Testing MQTT Functionality

You can test the server with public MQTT brokers:

- **test.mosquitto.org**: Public test broker (port 1883)
- **broker.emqx.io**: Public test broker (port 1883)
- **broker.hivemq.com**: Public test broker (port 1883)

### Debugging

The server logs to stderr, which you can monitor for debugging:
- Connection events
- Message reception
- Error conditions

## Security Considerations

- Use secure MQTT brokers (TLS) in production
- Implement proper authentication credentials
- Consider message encryption for sensitive data
- Monitor and limit message rate for public brokers

## License

MIT two-clause license applies to this project.

## Contributing

1. Follow the MCP server development guidelines
2. Ensure all MQTT operations handle errors gracefully
3. Add tests for new functionality
4. Update documentation for new features

## Support

For issues and questions:
- Check the MCP documentation: https://modelcontextprotocol.io/
- Review MQTT protocol specifications: https://mqtt.org/
- Test with public MQTT brokers before reporting connectivity issues

## Development

### Building and Publishing

To prepare the package for distribution:

1. Sync dependencies and update lockfile:
```bash
uv sync
```

2. Build package distributions:
```bash
uv build
```

This will create source and wheel distributions in the `dist/` directory.

### Debugging

Since MCP servers run over stdio, debugging can be challenging. For the best debugging
experience, we recommend using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).


Upon launching, the Inspector will display a URL that you can access in your browser to begin debugging.