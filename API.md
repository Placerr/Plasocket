# Plasocket Server Documentation

## Version 0.5.0

Welcome to the official documentation for the Plasocket Server! Plasocket is a lightweight, extensible WebSocket server designed for a pixel-based world game. It supports real-time multiplayer interaction, persistent world storage, and a robust plugin system to extend its functionality.

This document covers setup, configuration, API details for plugin development, and message protocols.

---

## Table of Contents

1.  [Introduction](#1-introduction)
2.  [Changelog](#2-changelog)
3.  [Features](#3-features)
4.  [Getting Started](#4-getting-started)
    * [Prerequisites](#prerequisites)
    * [Running the Server](#running-the-server)
5.  [Configuration (`server.conf`)](#5-configuration-serverconf)
6.  [World Data Management](#6-world-data-management)
    * [Run-Length Encoding (RLE)](#run-length-encoding-rle)
    * [Default World Generation](#default-world-generation)
7.  [Plugin Development](#7-plugin-development)
    * [Plugin Directory](#plugin-directory)
    * [Server API Class (`ServerAPI`)](#server-api-class-serverapi)
    * [Plugin Hooks](#plugin-hooks)
    * [Best Practices for Plugin Development](#best-practices-for-plugin-development)
8.  [Message Protocols](#8-message-protocols)
    * [Client-to-Server Messages](#client-to-server-messages)
    * [Server-to-Client Messages](#server-to-client-messages)
    * [Bidirectional Messages](#bidirectional-messages)
9.  [Constants](#9-constants)
    * [Block IDs (`BLOCK_IDS`)](#block-ids-block_ids)

---

## 1. Introduction

Plasocket provides a foundational backend for multiplayer pixel-art games. It manages client connections, synchronizes player movements, handles block modifications, and allows for extensive customization through its plugin architecture. The server is built with Python and leverages WebSockets for efficient real-time communication.

## 2. Changelog

### Plasocket 0.5.0 - The World Persistence Update

This release introduces significant enhancements to world management, including persistent world saving, block modification settings, and a more robust server architecture.

### New Features

* **Persistent World Saving & Loading**:
    * The server now automatically saves the world grid to `worlds/world.pw` at a configurable interval (`world_save_interval_s` in `server.conf`).
    * World data is loaded from `worlds/world.pw` on startup. If the file doesn't exist, a default world (grass, dirt, stone layers) is automatically generated.
    * World data is saved using an RLE (Run-Length Encoding) JSON format, making the world files more efficient.
    * A final world save is performed gracefully when the server is shut down (e.g., via Ctrl+C).
* **Configurable Block Modification (Read-Only Mode)**:
    * A new `block_modification` option in `server.conf` (defaulting to `false`) allows administrators to control whether clients can modify the world.
    * When `block_modification` is `false` (read-only mode), client-side `PLACE` and `ERASE` actions are immediately reverted by the server, providing a read-only experience.
* **Enhanced World Data Handling**:
    * The server now maintains an in-memory `WORLD_GRID` to represent the game world, allowing for efficient block updates and persistent storage.
    * RLE encoding/decoding functions (`rle_encode`, `rle_decode`) have been implemented for efficient world data transmission and storage.
* **Improved Dependency Management**:
    * The `check_and_install_dependencies` function is now called at the very beginning of `main` to ensure all necessary modules (like `websockets` and `configparser`) are available before the server attempts to use them.
    * The dependency check now forces a server restart if packages are installed, ensuring they are loaded correctly.
* **Refined Configuration Handling**:
    * The `server.conf` file now automatically includes any missing default configuration options when loaded, ensuring the configuration is always up-to-date with new server features without requiring manual edits.
    * More robust error handling for reading the `server.conf` file.
* **Internal API & Code Improvements**:
    * The `ServerAPI` class passed to plugins now includes a reference to the `websockets` module itself, allowing plugins more flexibility.
    * Refactored `main` function to separate setup and `asyncio.run` more cleanly.
    * Improved logging for block modifications and read-only mode actions.
    * Centralized global variables for better state management.
    * The server version is now exposed as `SERVER_VERSION = "0.5.0"`.

## 3. Features

* **Real-time Multiplayer**: Supports multiple clients connecting and interacting in a shared world.
* **Persistent World**: World state is saved to and loaded from a file (`worlds/world.pw`), ensuring continuity between server sessions.
* **Configurable Block Modification**: Server can operate in a read-write or read-only mode for block placement/erasure.
* **Plugin System**: Extensible architecture allowing custom Python plugins to add new game mechanics, commands, or server-side logic.
* **Texture Support**: Ability to send texture tilemap and title screen texture URLs to connected clients.
* **Basic Chat System**: Clients can send and receive chat messages.
* **Dependency Management**: Automatic checking and installation of required Python packages.
* **Configurable Server Settings**: `server.conf` file allows customization of host, port, plugin enabling, PVP, and more.

## 4. Getting Started

### Prerequisites

* Python 3.7+ installed on your system.

### Running the Server

1.  **Save the Server Code**: Save the provided Python code as `plasocket_server.py` (or any `.py` name).
2.  **Open Terminal/Command Prompt**: Navigate to the directory where you saved the file.
3.  **Run the Server**: Execute the script using Python:
    ```bash
    python plasocket_server.py
    ```
4.  **Dependency Installation**:
    * The first time you run the server, it will check for required packages (`websockets`, `configparser`).
    * It will prompt you to install them automatically. Type `y` and press Enter.
    * If packages are installed, the server will exit and ask you to restart it. Run the command again.
5.  **Configuration File**:
    * A `server.conf` file will be created in the same directory if it doesn't exist. You can edit this file to customize server settings.
6.  **World Directory**:
    * A `worlds` directory will be created, containing `world.pw` (the world data file).
    * A `plugins` directory will also be created for your custom plugins.

## 5. Configuration (`server.conf`)

The `server.conf` file allows you to customize various aspects of the Plasocket server. If this file doesn't exist, it will be created with default values upon first run.

```ini
[SERVER]
bind_to = 127.0.0.1           ; The IP address the server will listen on. '0.0.0.0' for all interfaces.
port = 5252                   ; The port the server will listen on.
plugins = true                ; Enable or disable the plugin loading system (true/false).
pvp = true                    ; Enable or disable Player vs. Player combat (true/false).
textures = false              ; Enable or disable sending texture information to clients (true/false).
texture_tilemap =             ; URL to the main texture tilemap image. Only sent if 'textures' is true.
title_texture =               ; URL to the title screen texture image. Only sent if 'textures' is true.
force_tilemap_load = false    ; If true, client is forced to load the texture tilemap.
log_messages = false          ; Enable or disable detailed logging of all received/sent messages (true/false).
texture_load_delay_main_s = 3.0 ; Delay in seconds after sending the main tilemap URL.
texture_load_delay_title_s = 1.0 ; Delay in seconds after sending the title texture URL.
block_modification = false    ; Enable or disable block modification by clients (true/false).
world_save_interval_s = 30.0  ; Interval in seconds between automatic world saves.
```

**Important Notes:**
* After modifying `server.conf`, you must restart the server for changes to take effect.
* If you delete `server.conf`, a new one with default values will be generated on the next server start.

## 6. World Data Management

Plasocket 0.5.0 introduces robust world persistence.

### Run-Length Encoding (RLE)

The server uses a custom Run-Length Encoding (RLE) format to efficiently store and transmit world grid data. This format compresses sequences of identical blocks.

The RLE data string is a comma-separated list of block representations. Each representation can be:
* An integer `block_id` (for a single block).
* `count`x`block_id` (for `count` consecutive blocks of the same `block_id`).

The data fills the grid row by row, from left to right, top to bottom.

**Example:**
`"10x1,0,0,0,2x1"` would decode to:
* 10 blocks of ID 1 (GRASS)
* 1 block of ID 0 (DIRT)
* 1 block of ID 0 (DIRT)
* 1 block of ID 0 (DIRT)
* 2 blocks of ID 1 (GRASS)

### Default World Generation

If `worlds/world.pw` does not exist on server startup, the server will automatically generate a default 100x60 world consisting of:
* A layer of `GRASS`
* Multiple layers of `DIRT` below the grass
* Layers of `STONE` extending to the bottom of the world

This default world is then saved to `world.pw`.

## 7. Plugin Development

Plasocket's plugin system allows you to extend server functionality without modifying the core server code.

### Plugin Directory

Plugins are standard Python files (`.py`) placed in the `plugins/` directory (created automatically by the server). The server will attempt to load all `.py` files in this directory that do not start with an underscore (`_`).

### Server API Class (`ServerAPI`)

Plugins receive an instance of the `ServerAPI` class, which provides methods to interact with the server, send messages to clients, and query server state.

#### `send_to_client(websocket, message_string)`
Sends a raw message string to a specific connected client.

* **`websocket`**: The `websockets.WebSocketServerProtocol` object representing the client's connection.
* **`message_string`**: The string message to send.

```python
await server_api_instance.send_to_client(websocket, "SERVER_MESSAGE|Hello, player!")
```

#### `broadcast(message_string, exclude_websocket=None)`
Broadcasts a message string to all currently connected clients.

* **`message_string`**: The string message to broadcast.
* **`exclude_websocket`** (optional): A `websockets.WebSocketServerProtocol` object to exclude from the broadcast (e.g., the client that sent the original message).

```python
await server_api_instance.broadcast("SERVER_MESSAGE|Everyone, gather round!")
await server_api_instance.broadcast(f"PLAYER_MESSAGE|SERVER|{username}|Just joined!", exclude_websocket=new_websocket)
```

#### `get_connected_clients()`
Returns a `set` of all currently connected `websockets.WebSocketServerProtocol` objects.

```python
connected_ws = server_api_instance.get_connected_clients()
for ws in connected_ws:
    print(f"Client connected: {ws.remote_address}")
```

#### `get_username_from_websocket(websocket)`
Retrieves the username associated with a given `websocket` connection.

* **`websocket`**: The `websockets.WebSocketServerProtocol` object.
* **Returns**: The username string, or `None` if the username is not found or not yet registered.

```python
username = server_api_instance.get_username_from_websocket(websocket)
if username:
    server_api_instance.log(f"User {username} sent a message.")
```

#### `is_pvp_enabled()`
Checks if Player vs. Player (PVP) combat is enabled on the server, as configured in `server.conf`.

* **Returns**: `True` if PVP is enabled, `False` otherwise.

```python
if server_api_instance.is_pvp_enabled():
    server_api_instance.log("PVP is enabled on this server.")
```

#### `log(message)`
Logs a message to the server console, specifically prefixed with `[PLUGIN API]`. This logging respects the `log_messages` setting in `server.conf` for certain message types.

* **`message`**: The string message to log.

```python
server_api_instance.log("My plugin is doing something important!")
```

#### `get_loaded_plugin_names()`
Returns a list of names (module names) of all successfully loaded plugins.

* **Returns**: A list of strings.

```python
plugin_list = server_api_instance.get_loaded_plugin_names()
print(f"Currently active plugins: {', '.join(plugin_list)}")
```

### Plugin Hooks

Plugins define specific asynchronous or synchronous functions that the server will call at various stages of its lifecycle or upon certain events.

#### `on_load(server_api_instance)`
Called once when the plugin is loaded during server startup. Use this for plugin initialization.

* **`server_api_instance`**: The `ServerAPI` instance for plugin interaction.
* **Can be `async` or synchronous.**

```python
# In your plugin file (e.g., my_plugin.py)

async def on_load(server_api_instance):
    server_api_instance.log("MyPlugin loaded successfully!")
    # Perform any setup tasks here
```

#### `on_connect(websocket, server_api_instance)`
Called when a new client establishes a WebSocket connection to the server.

* **`websocket`**: The `websockets.WebSocketServerProtocol` object for the new client.
* **`server_api_instance`**: The `ServerAPI` instance.
* **Can be `async` or synchronous.**

```python
# In your plugin file

async def on_connect(websocket, server_api_instance):
    username = server_api_instance.get_username_from_websocket(websocket) # May be None initially
    server_api_instance.log(f"New client connected: {websocket.remote_address}. Username: {username}")
    await server_api_instance.send_to_client(websocket, "SERVER_MESSAGE|Welcome to the Plasocket server!")
```

#### `on_message(websocket, message_str, message_parts, server_api_instance)`
Called when the server receives a message from a client.

* **`websocket`**: The `websockets.WebSocketServerProtocol` object of the sender.
* **`message_str`**: The raw string message received.
* **`message_parts`**: A list of strings, the result of splitting `message_str` by the `|` delimiter.
* **`server_api_instance`**: The `ServerAPI` instance.
* **Return Value**:
    * Return `True` if the plugin has fully handled the message and no further server processing (including default broadcasting or handling by other plugins) is desired for this message.
    * Return `False` or `None` (or simply omit a `return` statement) to allow the server to continue processing the message.
* **Can be `async` or synchronous.**

```python
# In your plugin file

async def on_message(websocket, message_str, message_parts, server_api_instance):
    username = server_api_instance.get_username_from_websocket(websocket)

    if len(message_parts) > 0 and message_parts[0] == "PLAYER_MESSAGE":
        if len(message_parts) > 3 and message_parts[3].startswith("!echo "):
            echo_text = message_parts[3][len("!echo "):]
            await server_api_instance.send_to_client(websocket, f"SERVER_MESSAGE|Echo from plugin: {echo_text}")
            return True # Message handled, prevent default chat broadcast

    if message_str == "HEARTBEAT":
        server_api_instance.log(f"Received heartbeat from {username}.")
        return True # Handled, no need for server to process as unknown
    
    return False # Allow server to process normally
```

#### `on_disconnect(websocket, server_api_instance)`
Called when a client disconnects from the server.

* **`websocket`**: The `websockets.WebSocketServerProtocol` object of the disconnected client.
* **`server_api_instance`**: The `ServerAPI` instance.
* **Can be `async` or synchronous.**

```python
# In your plugin file

async def on_disconnect(websocket, server_api_instance):
    username = server_api_instance.get_username_from_websocket(websocket)
    server_api_instance.log(f"Client disconnected: {websocket.remote_address}. Username: {username}")
    await server_api_instance.broadcast(f"SERVER_MESSAGE|{username} has left the game.")
```

### Best Practices for Plugin Development

* **Asynchronous Operations**: Plasocket uses `asyncio`. If your plugin performs I/O (network requests, file access) or long-running computations, use `await` with `asyncio`-compatible functions or `asyncio.to_thread` to avoid blocking the server's event loop.
* **Error Handling**: Wrap your plugin logic in `try...except` blocks to catch and log exceptions. Unhandled exceptions in plugin hooks can disrupt the server.
* **Return Values from `on_message`**: Clearly understand when to return `True` (message fully handled) versus `False` (allow default server processing).
* **Resource Management**: If your plugin opens files or connections, ensure they are properly closed (e.g., in `on_disconnect` or by using `asyncio.create_task` for background tasks that clean up).
* **Configuration**: For plugin-specific configuration, consider creating a separate config file for your plugin rather than modifying `server.conf` directly.
* **Modularity**: Keep your plugin code organized and modular.

## 8. Message Protocols

Messages sent between the client and server are string-based and typically delimited by the `|` character.

### Client-to-Server Messages

#### SYNC_REQ
Initial synchronization request from a client.
`USERNAME|SYNC_REQ|CLIENT_VERSION`
* `USERNAME`: The connecting player's desired username.
* `CLIENT_VERSION`: The client's software version.

#### PLACE
Request to place a block.
`PLACE|PLACERCLIENT|X|Y|BLOCK_ID`
* `X`, `Y`: Coordinates of the block.
* `BLOCK_ID`: The integer ID of the block to place.

#### ERASE
Request to erase (set to AIR) a block.
`ERASE|PLACERCLIENT|X|Y`
* `X`, `Y`: Coordinates of the block to erase.

#### PLAYER_MESSAGE
A standard chat message from a player.
`PLAYER_MESSAGE|PLACERCLIENT|USERNAME|MESSAGE_CONTENT`

### Server-to-Client Messages

#### JOIN_ACCEPT
Confirms successful connection and readiness for world data.
`JOIN_ACCEPT|PLACERSERVER|ME`

#### WORLD_DATA
Sends the entire world grid data.
`WORLD_DATA|PLACERSERVER|JSON_WORLD_PAYLOAD`
* `JSON_WORLD_PAYLOAD`: A JSON string containing `c2tilemap` (boolean), `width` (int), `height` (int), and `data` (RLE string).

```json
{
    "c2tilemap": true,
    "width": 100,
    "height": 60,
    "data": "100x1,100x0,..." // RLE encoded world data
}
```

#### SERVER_MESSAGE
A general message from the server to a specific client.
`SERVER_MESSAGE|MESSAGE_CONTENT`

#### TELLRAW
A server message intended for display as "raw text" (e.g., system messages).
`TELLRAW|PLACERSERVER|MESSAGE_CONTENT`

#### TEXTURE
Informs the client to load a specific texture tilemap.
`TEXTURE|PLACERSERVER|TILEMAP_URL`
* Used if `force_tilemap_load` is `false` in `server.conf`.

#### FORCE_TEXTURE
Forces the client to load a specific texture tilemap.
`FORCE_TEXTURE|PLACERSERVER|TILEMAP_URL`
* Used if `force_tilemap_load` is `true` in `server.conf`.

#### TITLE_TEXTURE
Informs the client to load a texture for the game title.
`TITLE_TEXTURE|PLACERSERVER|TITLE_TEXTURE_URL`

#### ERROR
Informs the client about an error.
`ERROR|SOURCE|ERROR_MESSAGE`
* `SOURCE`: Typically `SERVER` or `PLUGIN_NAME`.
* `ERROR_MESSAGE`: A descriptive error message.

### Bidirectional Messages

#### PLAYER_INFO
Updates player position and state.
`UUID|USERNAME|X|Y|DIRECTION|ANIMATION_FRAME|PLAYER_INFO`
* Typically sent by clients and then broadcast by the server to other clients.

## 9. Constants

### Block IDs (`BLOCK_IDS`)
A dictionary mapping common block names to their integer IDs.

```python
BLOCK_IDS = {
    "AIR": -1,
    "DIRT": 0,
    "GRASS": 1,
    "STONE": 2,
    "WOOD_LOG": 4,
    "COPPER": 9,
    "EMERALD": 10,
    "RUBY": 11,
    "DIAMOND": 12,
    "IRON": 13,
    "GOLD": 15,
    "LEAVES": 18,
}
