import asyncio

# --- Plugin Configuration ---
# IS_CORE_PLUGIN = True ensures this plugin loads before others,
# allowing it to intercept and optimize their messages.
IS_CORE_PLUGIN = True 

# --- Global State ---
# This cache will store the last PLAYER_INFO message sent for each player
# to each connected client. The structure is:
# {
#   websocket_client_1: {
#       "player_username_A": "full_message_string_for_A",
#       "player_username_B": "full_message_string_for_B"
#   },
#   websocket_client_2: { ... }
# }
last_player_info_cache = {}

# We need a reference to the original server API to send messages
# without causing an infinite loop.
original_server_api = None

async def optimizer_send_to_client(websocket, message):
    """
    Sends a message to a single client, but only if it's new data.
    """
    global last_player_info_cache, original_server_api
    
    parts = message.split('|')
    # We only optimize PLAYER_INFO messages as they are the most frequent.
    if len(parts) >= 7 and parts[6] == "PLAYER_INFO":
        player_key = parts[0] # The username of the player being updated
        
        # Check the cache for this specific client and player
        last_message = last_player_info_cache.get(websocket, {}).get(player_key)

        if message == last_message:
            # Data is identical, so we block the message to save bandwidth.
            return
        
        # Data is new, so we update the cache.
        if websocket in last_player_info_cache:
            last_player_info_cache[websocket][player_key] = message
    
    # Send the message using the original, un-hooked function.
    await original_server_api.send_to_client(websocket, message)


async def optimizer_broadcast_override(message, exclude_websocket=None):
    """
    This function replaces the default server broadcast. It loops through all
    clients and uses our optimizer_send_to_client logic for each one.
    """
    global original_server_api
    
    clients_to_send = [client for client in original_server_api.get_connected_clients() if client != exclude_websocket]
    
    # Create a task for each client so they can be processed in parallel.
    tasks = [optimizer_send_to_client(client, message) for client in clients_to_send]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def on_load(server_api):
    """
    Called when the plugin is loaded by the server.
    """
    global original_server_api
    if not original_server_api:
        original_server_api = server_api

    # This is the most important step: we tell the server to use our
    # custom broadcast function instead of its default one.
    server_api.set_broadcast_override(optimizer_broadcast_override)
    server_api.log("PingOptimizer: Network broadcast override is active. Optimizing traffic.")


def on_unload(server_api):
    """
    Called when the plugin is unloaded or reloaded.
    """
    global last_player_info_cache
    # Important to clear the override so the server can function if this plugin is removed.
    server_api.clear_broadcast_override()
    last_player_info_cache.clear()
    server_api.log("PingOptimizer: Network broadcast override released.")


async def on_connect(websocket, server_api):
    """
    Initializes a cache for a newly connected client.
    """
    global last_player_info_cache
    last_player_info_cache[websocket] = {}


async def on_disconnect(websocket, server_api):
    """
    Cleans up the cache for a disconnected client.
    """
    global last_player_info_cache
    last_player_info_cache.pop(websocket, None)
