import asyncio

# Stores the rainbow mode status for each client (websocket -> boolean)
# True if rainbow mode is active for that client
g_player_rainbow_modes = {}

# --- Plugin Hooks ---

def on_load(server_api):
    server_api.log("RainbowEffectPlugin: LETS DO SOME RAINBOWS!")

async def on_connect(websocket, server_api):
    # Initialize rainbow mode to False for new clients
    g_player_rainbow_modes[websocket] = False
    server_api.log(f"RainbowEffectPlugin: Client {websocket.remote_address} connected, rainbow mode OFF.")

async def on_disconnect(websocket, server_api):
    # Clean up rainbow mode status when a client disconnects
    if websocket in g_player_rainbow_modes:
        del g_player_rainbow_modes[websocket]
    server_api.log(f"RainbowEffectPlugin: Client {websocket.remote_address} disconnected, cleaned up rainbow status.")

async def _execute_rainbow_placement(x, y, server_api):
    """
    Asynchronously handles the rainbow block placement sequence at given X, Y.
    This is broadcast to all clients.
    The block IDs will cycle from 16 to 22, then 22 down to 16, repeatedly.
    """
    server_api.log(f"RainbowEffectPlugin: Starting rainbow sequence at ({x}, {y})")
    
    # Define the range for the rainbow effect
    min_block_id = 16
    max_block_id = 21

    # Loop indefinitely for the rainbow effect
    # In a real game, you might want a way to stop this loop,
    # e.g., if the player moves away or the plugin is unloaded.
    while True:
        # Cycle up from min_block_id to max_block_id
        for block_id_cycle in range(min_block_id, max_block_id + 1): # +1 to include max_block_id
            rainbow_message = f"PLACE|PLACERSERVER|{x}|{y}|{block_id_cycle}"
            await server_api.broadcast(rainbow_message)
            await asyncio.sleep(0.3)

        # Cycle down from max_block_id-1 to min_block_id (to avoid repeating max_block_id immediately)
        for block_id_cycle in range(max_block_id - 1, min_block_id - 1, -1): # -1 to include min_block_id
            rainbow_message = f"PLACE|PLACERSERVER|{x}|{y}|{block_id_cycle}"
            await server_api.broadcast(rainbow_message)
            await asyncio.sleep(0.3)

    server_api.log(f"RainbowEffectPlugin: Finished rainbow sequence at ({x}, {y})") # This line will only be reached if the loop breaks

async def on_message(websocket, message_string, message_parts, server_api):
    """
    Handles incoming messages for the rainbow plugin.
    """
    try:
        # --- Handle !rainbow command ---
        # Expected: PLAYER_MESSAGE|PLACERCLIENT|USERNAME|!rainbow
        if len(message_parts) == 4 and \
           message_parts[0] == "PLAYER_MESSAGE" and \
           message_parts[1] == "PLACERCLIENT" and \
           message_parts[3].lower() == "!rainbow":
            
            username = message_parts[2]
            current_mode = g_player_rainbow_modes.get(websocket, False)
            new_mode = not current_mode
            g_player_rainbow_modes[websocket] = new_mode
            
            status_message = "ON" if new_mode else "OFF"
            await server_api.send_to_client(websocket, f"SERVER_MESSAGE|RainbowMode|Your rainbow mode is now {status_message}")
            server_api.log(f"RainbowEffectPlugin: {username} ({websocket.remote_address}) toggled rainbow mode to {status_message}.")
            return True # Command handled

        # --- Handle PLACE command if rainbow mode is ON for the player ---
        # Expected: PLACE|PLACERCLIENT|X|Y|BLOCK_ID
        # Note: The client still sends PLACERCLIENT, the server plugin decides what to do.
        if len(message_parts) == 5 and \
           message_parts[0] == "PLACE" and \
           message_parts[1] == "PLACERCLIENT":
            
            if g_player_rainbow_modes.get(websocket, False): # Check if rainbow mode is ON for this player
                try:
                    x = message_parts[2]
                    y = message_parts[3]
                    # The original block_id (message_parts[4]) is ignored for the rainbow sequence.
                    
                    # Validate X and Y if necessary (e.g., ensure they are numbers)
                    # For simplicity, assuming they are valid as per your game's format.
                    # int(x) and int(y) could be used if they are expected as integers.

                    server_api.log(f"RainbowEffectPlugin: Intercepted PLACE from {websocket.remote_address} at ({x},{y}) with rainbow mode ON.")
                    
                    # Start the rainbow sequence as a background task
                    asyncio.create_task(_execute_rainbow_placement(x, y, server_api))
                    
                    return True # Placement handled by rainbow plugin (sequence started)
                except ValueError:
                    server_api.log(f"RainbowEffectPlugin: Invalid X or Y in PLACE message from {websocket.remote_address}: {message_string}")
                    # Optionally send an error back to the client
                    # await server_api.send_to_client(websocket, "ERROR|SERVER|Invalid coordinates for PLACE command.")
                    return False # Let server handle as malformed or ignore
                except Exception as e_place:
                    server_api.log(f"RainbowEffectPlugin: Error processing rainbow PLACE: {e_place}")
                    return False # Potentially let other handlers try

    except Exception as e:
        server_api.log(f"RainbowEffectPlugin: Error in on_message: {e}")
        # import traceback
        # server_api.log(traceback.format_exc())

    return False # Message not handled by this plugin or an error occurred before handling
