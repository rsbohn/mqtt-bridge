# GitHub Copilot Instructions for MCP-MQTT Server

<!-- Use this file to provide workspace-specific custom instructions to Copilot. For more details, visit https://code.visualstudio.com/docs/copilot/copilot-customization#_use-a-githubcopilotinstructionsmd-file -->

This is an MCP (Model Context Protocol) server project that provides MQTT communication capabilities. Please use the get_vscode_api with a query as input to fetch the latest VS Code API references when working with VS Code-related functionality.

## Project Overview

This MCP server enables LLMs to interact with MQTT brokers through the Model Context Protocol. It provides tools for:

- Connecting to MQTT brokers
- Publishing messages to topics
- Subscribing to topics and receiving messages
- Managing multiple MQTT connections
- Monitoring connection status and message history

## Key Technologies

- **Python 3.12+**: Core language
- **MCP SDK**: Model Context Protocol implementation
- **paho-mqtt**: MQTT client library
- **asyncio-mqtt**: Asynchronous MQTT support

## Development Guidelines

1. **Logging**: Always use `logging` to stderr, never print to stdout (STDIO transport requirement)
2. **Error Handling**: Wrap MQTT operations in try-except blocks
3. **Resource Management**: Properly manage MQTT client connections and cleanup
4. **Schema Validation**: Use JSON Schema for tool input validation
5. **State Management**: Maintain connection state and message history

## MCP Server Patterns

- Use `@server.list_tools()` for tool discovery
- Use `@server.call_tool()` for tool execution
- Use `@server.list_resources()` for resource listing
- Use `@server.read_resource()` for resource content
- Use `@server.list_prompts()` and `@server.get_prompt()` for prompt templates

## References

- MCP SDK Documentation: https://github.com/modelcontextprotocol/create-python-server
- More info and examples: https://modelcontextprotocol.io/llms-full.txt
- MQTT Protocol: https://mqtt.org/
- Paho MQTT Client: https://pypi.org/project/paho-mqtt/

## Testing

When testing MQTT functionality:
- Test local first: 192.168.0.185:1883
- Use public test brokers like `test.mosquitto.org` or `broker.emqx.io`
- Test with different QoS levels (0, 1, 2)
- Verify wildcard subscriptions (+ and # patterns)
- Test connection persistence and reconnection scenarios

## Development Environment

### Git Operations
- Use meaningful commit messages that describe the purpose of the changes
- Remember to check status with `git status` before committing
- On Windows: Always use `wsl git` for all Git operations (e.g., `wsl git add`, `wsl git commit`, etc.)

### Code Formatting
- Use `black` for Python code formatting to maintain consistent code style
- Black enforces PEP 8 compliant formatting with some specific style choices
- Always run `black` on Python files before committing: `black filename.py`

### Shell Environment
- Use PowerShell on Windows for running terminal commands
- When executing Python scripts, use the appropriate virtual environment
- For long-running processes like server instances, use separate terminal sessions

## Special Commands

When I start a request with `!unsafe`, I am asking for an action that might be irreversible. When this happens:
1. Show what will happen first (preview the action)
2. Ask just once "Are you sure?" for confirmation
3. Proceed immediately if confirmed

Our local MQTT broker is running on `192.168.0.185:1883`.
Always subscribe to `dev/+/debug` for debugging messages.