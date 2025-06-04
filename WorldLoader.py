import asyncio
import os # For path manipulation and checks
# No need for re for this approach, os.path is safer for path validation

# Store the base directory for worlds for security checks
BASE_WORLDS_DIR = os.path.abspath("worlds")

def on_load(server_api):
    server_api.log("WorldLoaderPlugin: Loaded successfully.")
    if not os.path.exists(BASE_WORLDS_DIR):
        server_api.log(f"WorldLoaderPlugin: Warning - '{BASE_WORLDS_DIR}' directory does not exist. Creating it.")
        os.makedirs(BASE_WORLDS_DIR, exist_ok=True)


async def on_message(websocket, message_string, message_parts, server_api):
    """
    Handles messages to load world files.
    Expected format: PLAYER_MESSAGE|PLACERCLIENT|USERNAME|!load_world {filename}
    """
    try:
        # Check basic message structure
        if not (len(message_parts) == 4 and \
                message_parts[0] == "PLAYER_MESSAGE" and \
                message_parts[1] == "PLACERCLIENT"): # Client sends PLACERCLIENT
            return False # Not for this plugin or malformed for its interest

        username = message_parts[2] # Username of the player who sent the command
        command_full = message_parts[3]

        # Check if it's the !load_world command
        if not command_full.startswith("!load_world "):
            return False # Not the command we're looking for

        command_args = command_full.split(" ", 1)
        if len(command_args) < 2 or not command_args[1].strip():
            await server_api.send_to_client(websocket, "ERROR|WORLD_LOADER|No filename provided for !load_world.")
            server_api.log(f"WorldLoaderPlugin: {username} tried !load_world without a filename.")
            return True # Command recognized, error sent

        requested_file_name = command_args[1].strip()

        # --- Security Validations for filename ---
        # 1. Basic sanity check for filename characters (avoiding path traversal in the name itself)
        if ".." in requested_file_name or "/" in requested_file_name or "\\" in requested_file_name:
            await server_api.send_to_client(websocket, f"ERROR|WORLD_LOADER|Invalid characters in filename: {requested_file_name}")
            server_api.log(f"WorldLoaderPlugin: {username} attempted to load invalid filename: {requested_file_name}")
            return True

        # 2. Construct the full path and ensure it's within the designated 'worlds' directory
        #    This is the most crucial security step.
        target_file_path = os.path.join(BASE_WORLDS_DIR, requested_file_name)

        # Normalize the path (e.g., resolve 'A/../B' to 'B') and make it absolute
        normalized_target_path = os.path.abspath(target_file_path)

        if not normalized_target_path.startswith(BASE_WORLDS_DIR):
            await server_api.send_to_client(websocket, f"ERROR|WORLD_LOADER|Access denied to file: {requested_file_name}")
            server_api.log(f"WorldLoaderPlugin: {username} attempted path traversal: {requested_file_name} (resolved to {normalized_target_path})")
            return True

        # --- Load and Send World ---
        server_api.log(f"WorldLoaderPlugin: {username} attempting to load world: {normalized_target_path}")
        try:
            with open(normalized_target_path, 'r', encoding='utf-8') as f:
                world_content = f.read()

            # Send the world data first
            response_message = f"WORLD_DATA|PLACERSERVER|{world_content}"
            await server_api.send_to_client(websocket, response_message)
            server_api.log(f"WorldLoaderPlugin: Sent world '{requested_file_name}' to {username}.")

            # MODIFICATION: Send the SET_POSITION command after sending world data
            set_position_message = f"SET_POSITION|PLACERSERVER|100|100|{username}"
            await server_api.send_to_client(websocket, set_position_message)
            server_api.log(f"WorldLoaderPlugin: Sent SET_POSITION command for {username} to 100,100 after loading world.")

            return True # Message handled

        except FileNotFoundError:
            await server_api.send_to_client(websocket, f"ERROR|WORLD_LOADER|World file not found: {requested_file_name}")
            server_api.log(f"WorldLoaderPlugin: {username} requested non-existent world: {requested_file_name}")
            return True # Message handled (error reported)

        except Exception as e:
            await server_api.send_to_client(websocket, f"ERROR|WORLD_LOADER|Could not load world '{requested_file_name}': {type(e).__name__}")
            server_api.log(f"WorldLoaderPlugin: Error loading world '{requested_file_name}' for {username}: {e}")
            # Optionally log traceback for server admin:
            # import traceback
            # server_api.log(traceback.format_exc())
            return True # Message handled (error reported)

    except Exception as e:
        # Catch-all for unexpected errors within the plugin's message handler
        server_api.log(f"WorldLoaderPlugin: CRITICAL ERROR in on_message: {e}")
        # import traceback
        # server_api.log(traceback.format_exc())
        # It's generally safer not to send detailed errors to client here,
        # but acknowledge if possible or just log heavily.
        # Depending on the error, might not even be able to send to client.
        return False # Let other handlers try or default server logic to report generic error.

    return False # Default: message not handled by this plugin
