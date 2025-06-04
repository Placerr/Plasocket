import asyncio
import json
import os

# --- Plugin State ---
# Global counter for unique NPC IDs
g_next_npc_id = 0
# Dictionary to store details of active NPCs
# Format: {npc_id: {"name": str, "skin": str, "x": int, "y": int, "hp": int, "creator_username": str, "commands": list[str]}}
g_active_npcs = {} 
# Dictionary to map NPC name (lowercase) to NPC ID for quicker lookup
g_npc_names_to_ids = {}

# Stores player positions keyed by USERNAME: {username: {"x": int, "y": int}}
g_player_locations = {}

# Task for periodic NPC broadcast
g_npc_broadcast_task = None

# --- Persistence Configuration ---
NPC_DATA_FILE = "plugins/npcs.json"
CNPC_FOLDER = "plugins/CNPC" # Folder for CNPC specific data

# --- Utility Functions for Persistence ---
def _load_npcs():
    """Loads NPC data from npcs.json."""
    global g_active_npcs, g_next_npc_id, g_npc_names_to_ids
    
    # Ensure the CNPC folder exists
    if not os.path.exists(CNPC_FOLDER):
        os.makedirs(CNPC_FOLDER)
        print(f"CNPC Plugin: Created CNPC data directory: {CNPC_FOLDER}")

    file_path = os.path.join(CNPC_FOLDER, "npcs.json")
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                loaded_data = json.load(f)
                g_active_npcs = {int(k): v for k, v in loaded_data.items()} # Ensure keys are int
            
            # Rebuild g_npc_names_to_ids and find next_npc_id
            max_id = -1
            g_npc_names_to_ids = {}
            for npc_id, npc_data in g_active_npcs.items():
                g_npc_names_to_ids[npc_data["name"].lower()] = npc_id
                if npc_id > max_id:
                    max_id = npc_id
            g_next_npc_id = max_id + 1
            
            print(f"CNPC Plugin: Loaded {len(g_active_npcs)} NPCs from {file_path}")
        except json.JSONDecodeError:
            print(f"CNPC Plugin: Error decoding {file_path}. Starting with empty NPC database.")
            g_active_npcs = {}
            g_npc_names_to_ids = {}
            g_next_npc_id = 0
        except Exception as e:
            print(f"CNPC Plugin: An error occurred loading NPCs from {file_path}: {e}")
            g_active_npcs = {}
            g_npc_names_to_ids = {}
            g_next_npc_id = 0
    else:
        print(f"CNPC Plugin: {file_path} not found. Starting with empty NPC database.")
        g_active_npcs = {}
        g_npc_names_to_ids = {}
        g_next_npc_id = 0

def _save_npcs():
    """Saves current NPC data to npcs.json."""
    file_path = os.path.join(CNPC_FOLDER, "npcs.json")
    try:
        with open(file_path, 'w') as f:
            json.dump(g_active_npcs, f, indent=4)
        print(f"CNPC Plugin: Saved {len(g_active_npcs)} NPCs to {file_path}")
    except IOError as e:
        print(f"CNPC Plugin: Error saving NPCs to {file_path}: {e}")

# --- Periodic NPC Broadcast Task ---
async def _periodic_npc_broadcast(server_api):
    """
    Periodically broadcasts PLAYER_INFO for all active NPCs to all connected clients.
    """
    while True:
        try:
            # Iterate over a copy to avoid issues if g_active_npcs is modified during iteration
            for npc_id, npc_data in list(g_active_npcs.items()):
                npc_info_message = (
                    f"{npc_data['name']}|{npc_data['x']}|{npc_data['y']}|{npc_data['skin']}|{npc_id}|{npc_data['hp']}|PLAYER_INFO"
                )
                await server_api.broadcast(npc_info_message)
            # server_api.log(f"CNPC Plugin: Broadcasted info for {len(g_active_npcs)} NPCs.") # Too verbose
        except asyncio.CancelledError:
            server_api.log("CNPC Plugin: Periodic NPC broadcast task cancelled.")
            break
        except Exception as e:
            server_api.log(f"CNPC Plugin: Error in periodic NPC broadcast task: {e}")
        
        await asyncio.sleep(1/30) # Broadcast approximately 30 times per second

# --- Plugin Hooks ---

def on_load(server_api):
    """
    Called when the plugin is loaded by the server.
    Initializes the plugin and logs a message.
    """
    global g_npc_broadcast_task
    server_api.log("CNPC Plugin: Initializing...")
    _load_npcs() # Load NPCs on startup
    server_api.log("CNPC Plugin: Loaded. Use !npc create <name> <skin> [x] [y] to create NPCs.")
    server_api.log("CNPC Plugin: Use !npc cmd <ID> add <command> to assign commands to NPCs.")
    server_api.log("CNPC Plugin: Use !npc cmd <ID> clear to remove all commands from an NPC.")
    server_api.log("CNPC Plugin: NPC commands support %player% (damaging player) and %npc% (NPC name) placeholders.")
    server_api.log("CNPC Plugin: IMPORTANT: Client sends DAMAGE|PLACERCLIENT|{npc_name}|{damaging_username} for NPC damage.")

    # Start the periodic NPC broadcast task
    g_npc_broadcast_task = asyncio.create_task(_periodic_npc_broadcast(server_api))
    server_api.log("CNPC Plugin: Started periodic NPC broadcast task.")


async def on_connect(websocket, server_api):
    """
    Called when a client connects. Sends all active NPC data for syncing.
    (This is now partially redundant with periodic broadcast, but good for immediate sync)
    """
    server_api.log(f"CNPC Plugin: Client {websocket.remote_address} connected. Syncing NPCs...")
    # Send all active NPCs to the newly connected client immediately
    for npc_id, npc_data in g_active_npcs.items():
        npc_info_message = (
            f"{npc_data['name']}|{npc_data['x']}|{npc_data['y']}|{npc_data['skin']}|{npc_id}|{npc_data['hp']}|PLAYER_INFO"
        )
        await server_api.send_to_client(websocket, npc_info_message)
        # server_api.log(f"CNPC Plugin: Sent NPC {npc_data['name']} (ID:{npc_id}) to new client {websocket.remote_address}") # Too verbose
    server_api.log(f"CNPC Plugin: Finished immediate sync of {len(g_active_npcs)} NPCs to {websocket.remote_address}.")


async def on_disconnect(websocket, server_api):
    """
    Called when a client disconnects. Cleans up their location from the plugin's state.
    """
    disconnected_username = server_api.get_username_from_websocket(websocket)
    if disconnected_username:
        if disconnected_username in g_player_locations:
            del g_player_locations[disconnected_username]
            server_api.log(f"CNPC Plugin: Cleaned up location for {disconnected_username} on disconnect.")
        server_api.log(f"CNPC Plugin: Client {disconnected_username} ({websocket.remote_address}) disconnected.")
    else:
        server_api.log(f"CNPC Plugin: Client {websocket.remote_address} disconnected (username unknown).")

def on_unload(server_api):
    """
    Called when the plugin is unloaded. Cancels the periodic broadcast task.
    """
    global g_npc_broadcast_task
    if g_npc_broadcast_task:
        g_npc_broadcast_task.cancel()
        server_api.log("CNPC Plugin: Cancelled periodic NPC broadcast task during unload.")


async def on_message(websocket, message_string, message_parts, server_api):
    """
    Handles incoming messages for the CNPC plugin.
    Processes the '!npc create' command, '!npc cmd' command, and 'DAMAGE' messages,
    and tracks PLAYER_INFO.
    """
    global g_next_npc_id # Declare intent to modify the global variable

    # --- Track PLAYER_INFO messages (always sent by client, contains location) ---
    # Expected format: USERNAME|X|Y|SKIN|ANIMATION_FRAME|HEALTH|PLAYER_INFO
    if len(message_parts) == 7 and message_parts[6] == "PLAYER_INFO":
        username = message_parts[0] # The username is the first part
        player_x = int(message_parts[1])
        player_y = int(message_parts[2])
            
        # Store location keyed by username
        g_player_locations[username] = {"x": player_x, "y": player_y}
            # server_api.log(f"CNPC Plugin: Updated location for {username} to ({player_x},{player_y}).") # Too verbose for frequent updates
        return True # IMPORTANT: Return True to indicate this plugin handled the message

    # --- Handle SEND|PLACERCLIENT messages (to prevent broadcasting) ---
    # If the client sends a "SEND" message, it's typically for internal client processing.
    # We explicitly handle it here to prevent the main server from broadcasting it.
    # Expected format: SEND|PLACERCLIENT|...
    if len(message_parts) >= 2 and message_parts[0] == "SEND" and message_parts[1] == "PLACERCLIENT":
        return True # Handled, do not broadcast

    # --- Handle !npc create command ---
    # Expected format: PLAYER_MESSAGE|PLACERCLIENT|USERNAME|!npc create <name> <skin> [x] [y]
    if len(message_parts) >= 4 and \
       message_parts[0] == "PLAYER_MESSAGE" and \
       message_parts[1] == "PLACERCLIENT" and \
       message_parts[3].lower().startswith("!npc create"):
        
        command_sender_username = message_parts[2] # Get the username of the player sending the command
        command_args = message_parts[3].split(' ') 
        
        npc_name = command_args[2] if len(command_args) > 2 else None
        npc_skin = command_args[3] if len(command_args) > 3 else None
        
        target_x = None
        target_y = None

        # Determine if X and Y coordinates are provided or if sender's location should be used
        if len(command_args) == 6: # Full command: !npc create <name> <skin> <x> <y>
            try:
                target_x = int(command_args[4])
                target_y = int(command_args[5])
            except ValueError:
                await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Error: Invalid X or Y coordinates. Usage: !npc create <name> <skin> [x] [y]")
                server_api.log(f"CNPC Plugin: Invalid NPC creation command (ValueError) from {websocket.remote_address}: {message_string}")
                return True # Message handled (with an error response)
        elif len(command_args) == 4: # Command without X, Y: !npc create <name> <skin>
            # Retrieve location using the command sender's username
            player_location = g_player_locations.get(command_sender_username) 
            
            # Check if location is available and not the default (0,0) or None
            if player_location and (player_location['x'] != 0 or player_location['y'] != 0):
                target_x = player_location['x']
                target_y = player_location['y']
                server_api.log(f"CNPC Plugin: Using sender's last known location ({target_x},{target_y}) for NPC creation by {command_sender_username}.")
            else:
                await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Error: Your location is unknown or still at origin. Please move your player first, then try again, or specify X, Y coordinates. Usage: !npc create <name> <skin> [x] [y]")
                server_api.log(f"CNPC Plugin: Cannot create NPC, sender's location unknown or at origin for {command_sender_username} ({websocket.remote_address}).")
                return True # Message handled (with an error response)
        else:
            # Incorrect number of arguments
            await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Usage: !npc create <name> <skin> [x] [y]")
            return True # Message handled (with usage instructions)

        # Basic validation for name and skin
        if npc_name is None or npc_skin is None or target_x is None or target_y is None:
             await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Error: Missing NPC name, skin, or location. Usage: !npc create <name> <skin> [x] [y]")
             return True

        try:
            # Assign a unique ID to the NPC
            npc_id = g_next_npc_id
            g_next_npc_id += 1 # Increment for the next NPC

            # Set a default HP for the NPC
            npc_hp = 100 

            # Construct the PLAYER_INFO message for the NPC
            # The format is: USERNAME|X|Y|SKIN|ID|HEALTH|PLAYER_INFO
            npc_info_message = (
                f"{npc_name}|{target_x}|{target_y}|{npc_skin}|{npc_id}|{npc_hp}|PLAYER_INFO"
            )

            server_api.log(f"CNPC Plugin: Broadcasting NPC PLAYER_INFO: {npc_info_message}")

            # Store the NPC details, including an empty command list initially
            g_active_npcs[npc_id] = {
                "name": npc_name,
                "skin": npc_skin,
                "x": target_x,
                "y": target_y,
                "hp": npc_hp,
                "creator_username": command_sender_username,
                "commands": [] # Initialize commands as an empty list
            }
            g_npc_names_to_ids[npc_name.lower()] = npc_id # Store name-to-ID mapping

            _save_npcs() # Save NPCs after creation

            server_api.log(f"CNPC Plugin: Creating NPC '{npc_name}' (ID: {npc_id}) at ({target_x},{target_y}) with skin '{npc_skin}'.")
            
            # Broadcast the NPC's info to all connected clients
            await server_api.broadcast(npc_info_message)
            
            # Inform the command sender that the NPC was created
            await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|NPC '{npc_name}' created (ID: {npc_id}).")
            
            return True # Indicate that this plugin handled the message
        
        except Exception as e:
            # Catch any other unexpected errors during NPC creation
            server_api.log(f"CNPC Plugin: An unexpected error occurred while creating NPC: {e}")
            await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|Error creating NPC: {e}")
            return True # Message handled (with an error response)

    # --- Handle !npc cmd command ---
    # Expected format: PLAYER_MESSAGE|PLACERCLIENT|USERNAME|!npc cmd <ID> <action> [command_string]
    elif len(message_parts) == 4 and \
         message_parts[0] == "PLAYER_MESSAGE" and \
         message_parts[1] == "PLACERCLIENT" and \
         message_parts[3].lower().startswith("!npc cmd"):
        
        command_sender_username = message_parts[2]
        # Split the command string itself
        command_args = message_parts[3].split(' ', 4) # Split up to 4 times for action and command_string
        
        if len(command_args) >= 3: # Expecting: !npc, cmd, ID, [action], [command_string]
            try:
                npc_id = int(command_args[2])
                action = command_args[3].lower() if len(command_args) > 3 else None

                if npc_id not in g_active_npcs:
                    await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|Error: NPC with ID {npc_id} not found.")
                    server_api.log(f"CNPC Plugin: NPC ID {npc_id} not found for command action by {command_sender_username}.")
                    return True

                if action == "add" and len(command_args) >= 5: # !npc cmd ID add command_string
                    npc_command_string = command_args[4]
                    g_active_npcs[npc_id]["commands"].append(npc_command_string)
                    _save_npcs() # Save after modification
                    server_api.log(f"CNPC Plugin: User {command_sender_username} added command '{npc_command_string}' to NPC ID {npc_id}.")
                    await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|Command '{npc_command_string}' added to NPC ID {npc_id}.")
                    return True
                elif action == "clear": # !npc cmd ID clear
                    g_active_npcs[npc_id]["commands"] = []
                    _save_npcs() # Save after modification
                    server_api.log(f"CNPC Plugin: User {command_sender_username} cleared commands for NPC ID {npc_id}.")
                    await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|Commands cleared for NPC ID {npc_id}.")
                    return True
                else:
                    await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Usage: !npc cmd <ID> add <command> OR !npc cmd <ID> clear")
                    return True
            except ValueError:
                await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Error: Invalid NPC ID. Usage: !npc cmd <ID> add <command> OR !npc cmd <ID> clear")
                server_api.log(f"CNPC Plugin: Invalid NPC command (ValueError) from {websocket.remote_address}: {message_string}")
                return True # Command handled (with error)
            except Exception as e:
                server_api.log(f"CNPC Plugin: An unexpected error occurred while assigning NPC command: {e}")
                await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|Error assigning NPC command: {e}")
                return True # Command handled (with error)
        else:
            await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Usage: !npc cmd <ID> add <command> OR !npc cmd <ID> clear")
            return True # Command handled (with usage instructions)

    # --- Handle DAMAGE message ---
    # Expected: DAMAGE|PLACERCLIENT|{npc_name_damaged}|{damaging_username}
    elif len(message_parts) == 4 and message_parts[0] == "DAMAGE" and message_parts[1] == "PLACERCLIENT":
        damaged_entity_name = message_parts[2] # This is the NPC name
        damaging_username = message_parts[3] # This is the player's username that damaged the NPC
        
        if not damaging_username: # Should not happen if client sends it, but good for safety
            server_api.log(f"CNPC Plugin: Could not identify damaging user for DAMAGE message from {websocket.remote_address}. Ignoring.")
            await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Error: Could not identify your username for damage action.")
            return True # Handled (with error)

        # Look up the NPC ID by name
        npc_id_damaged = g_npc_names_to_ids.get(damaged_entity_name.lower())

        if npc_id_damaged is None:
            # If it's not a known NPC name, it might be a player-to-player damage.
            # In this case, we let the main server or another plugin handle it.
            server_api.log(f"CNPC Plugin: Received DAMAGE for unknown entity '{damaged_entity_name}'. Passing to next handler.")
            return False 
        
        # If we found the NPC ID, proceed with NPC damage logic
        
        # Always broadcast the original damage message for visual effects, regardless of PVP setting
        response_message = f"DAMAGE|PLACERSERVER|{damaged_entity_name}"
        await server_api.broadcast(response_message)
        server_api.log(f"CNPC Plugin: Broadcasted DAMAGE to NPC '{damaged_entity_name}' by {damaging_username}.")

        # Check if the damaged NPC has commands assigned (this runs regardless of PVP setting)
        if npc_id_damaged in g_active_npcs and g_active_npcs[npc_id_damaged]["commands"]:
            for saved_command in g_active_npcs[npc_id_damaged]["commands"]:
                # Replace placeholders before sending
                processed_command = saved_command.replace("%player%", damaging_username)
                processed_command = processed_command.replace("%npc%", damaged_entity_name)

                # Determine how to send the command based on its format
                command_parts_for_check = processed_command.split('|')
                
                # Check if it's a server-prefixed command (e.g., TELLRAW|PLACERSERVER|...)
                # Need at least 2 parts to check the second part.
                if len(command_parts_for_check) >= 2 and command_parts_for_check[1] == "PLACERSERVER":
                    # It's a server-prefixed command, send it wrapped in SEND|PLACERSERVER
                    command_to_send = f"{processed_command}"
                    server_api.log(f"CNPC Plugin: NPC '{damaged_entity_name}' (ID: {npc_id_damaged}) damaged, sending wrapped command to {damaging_username}: '{processed_command}'")
                    await server_api.send_to_client(websocket, command_to_send)
                else:
                    # It's not a server-prefixed command, broadcast it directly
                    server_api.log(f"CNPC Plugin: NPC '{damaged_entity_name}' (ID: {npc_id_damaged}) damaged, broadcasting direct command: '{processed_command}'")
                    await server_api.broadcast(processed_command) # Broadcast directly
        else:
            server_api.log(f"CNPC Plugin: NPC '{damaged_entity_name}' (ID: {npc_id_damaged}) damaged but no commands assigned.")
            
        # If PVP is disabled, send a specific message to the damaging player.

        return True # Message handled by this plugin

    return False # Indicate that this plugin did not handle the message
