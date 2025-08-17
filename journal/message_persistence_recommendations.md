# MCP-MQTT Message Persistence Enhancement Recommendations

## Current State Analysis
- **Storage**: In-memory list (non-persistent)
- **Lifecycle**: Messages lost on server restart
- **Limit**: Processes last 100 messages, returns max 20
- **Memory**: Unbounded growth potential

## Recommended Improvements

### 1. Circular Buffer Implementation
```python
from collections import deque

# Replace: received_messages: List[dict] = []
received_messages: deque = deque(maxlen=1000)  # Auto-removes old messages
```

### 2. Optional File Persistence
```python
import json
from pathlib import Path

MESSAGE_CACHE_FILE = Path("~/.mcp-mqtt/message_cache.json").expanduser()

def save_messages_to_disk():
    """Save recent messages to disk for persistence."""
    MESSAGE_CACHE_FILE.parent.mkdir(exist_ok=True)
    with open(MESSAGE_CACHE_FILE, 'w') as f:
        json.dump(list(received_messages), f, indent=2)

def load_messages_from_disk():
    """Load messages from disk on startup."""
    if MESSAGE_CACHE_FILE.exists():
        with open(MESSAGE_CACHE_FILE, 'r') as f:
            return deque(json.load(f), maxlen=1000)
    return deque(maxlen=1000)
```

### 3. Environment-Based Configuration
```python
import os

# Configuration
MAX_MESSAGES = int(os.getenv("MCP_MQTT_MAX_MESSAGES", "1000"))
PERSIST_MESSAGES = os.getenv("MCP_MQTT_PERSIST", "false").lower() == "true"
CACHE_FILE = os.getenv("MCP_MQTT_CACHE_FILE", "~/.mcp-mqtt/messages.json")
```

### 4. Message Retention Policies
```python
from datetime import datetime, timedelta

def cleanup_old_messages(max_age_hours=24):
    """Remove messages older than specified hours."""
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    global received_messages
    received_messages = deque([
        msg for msg in received_messages 
        if datetime.fromisoformat(msg['timestamp']) > cutoff
    ], maxlen=MAX_MESSAGES)
```

### 5. Database Option (Advanced)
```python
import sqlite3
from contextlib import contextmanager

@contextmanager
def get_db_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect("~/.mcp-mqtt/messages.db")
    try:
        yield conn
    finally:
        conn.close()

def store_message_in_db(msg_data):
    """Store message in SQLite database."""
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO messages (topic, payload, qos, retain, timestamp, connection_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (msg_data['topic'], msg_data['payload'], msg_data['qos'], 
              msg_data['retain'], msg_data['timestamp'], msg_data['connection_id']))
        conn.commit()
```

## Implementation Priority

### Phase 1: Immediate (Memory Management)
- ✅ Replace list with `collections.deque` with maxlen
- ✅ Add message count limits
- ✅ Prevent unbounded memory growth

### Phase 2: Short-term (Basic Persistence)
- 📝 Add optional file-based caching
- 📝 Environment variable configuration
- 📝 Message age-based cleanup

### Phase 3: Long-term (Advanced Features)
- 🔮 SQLite database storage
- 🔮 Message search and filtering
- 🔮 Retention policy configuration
- 🔮 Message statistics and analytics

## Configuration Example
```bash
# Environment variables for enhanced persistence
export MCP_MQTT_MAX_MESSAGES=2000
export MCP_MQTT_PERSIST=true
export MCP_MQTT_CACHE_FILE="/path/to/custom/cache.json"
export MCP_MQTT_MAX_AGE_HOURS=48
```
