import asyncio
import json
import os
import traceback
import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

# --- Plugin Configuration ---
# Establishes the folder structure and file paths for the plugin's configuration.
PLUGIN_FOLDER = "plugins/SuperLobby"
CONFIG_FILE = os.path.join(PLUGIN_FOLDER, "config.json")
# Optional: Place a .ttf font file in the plugin folder for custom text rendering.
FONT_FILE = os.path.join(PLUGIN_FOLDER, "font.ttf")
# The plugin will read the main server's admin file.
ADMIN_FILE_PATH = "admins.json"

# --- Default Configuration ---
# Provides a fallback configuration to ensure the plugin works on first launch
# and to handle new settings added in updates.
DEFAULT_CONFIG = {
    "spawn_location": None, # Will be an object like {"x": 100, "y": 100}
    "join_message": {
        "text": "Welcome to the Server!",
        "color": "white",
        "duration_s": 5
    },
    "server_rules": [
        "1. Be respectful to all players.",
        "2. No cheating or exploiting bugs.",
        "3. Do not spam the chat."
    ],
    "muted_players": [],
    "periodic_broadcast": {
        "enabled": True,
        "interval_s": 300, # 5 minutes
        "message": "[SERVER] Don't forget to read the !!rules and have fun!"
    }
}

# --- Global State ---
config = {}
player_locations = {} # Caches the last known location of players in the main world.
broadcast_task = None # Holds the asyncio task for the periodic broadcast.
plugin_font = None # Holds the loaded font object for image generation.
ADMIN_USERS = set() # Holds the set of admin usernames, loaded from admins.json.
# --- NEW: A set to track players who have just joined and need to be teleported ---
players_awaiting_spawn = set()

# --- Utility & Helper Functions ---

def load_config(server_api):
    """
    Loads the configuration from config.json. If the file doesn't exist,
    it creates one with default values. It also merges new default settings
    into existing config files.
    """
    global config
    if not os.path.exists(PLUGIN_FOLDER):
        os.makedirs(PLUGIN_FOLDER)
        server_api.log("SuperLobby: Created plugin folder.")

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            # Merge missing keys from default config
            updated = False
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
                    updated = True
            if updated:
                save_config(server_api)
        except json.JSONDecodeError:
            server_api.log("SuperLobby: Error reading config.json. Overwriting with defaults.")
            config = DEFAULT_CONFIG.copy()
            save_config(server_api)
    else:
        config = DEFAULT_CONFIG.copy()
        save_config(server_api)
    server_api.log("SuperLobby: Configuration loaded.")

def save_config(server_api):
    """Saves the current configuration state to config.json."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        server_api.log(f"SuperLobby: CRITICAL ERROR saving config.json: {e}")

def load_font(server_api):
    """
    Loads a TTF font for generating text images. Falls back to a system font
    or a default built-in font if the custom one is not found.
    """
    global plugin_font
    font_size = 60
    try:
        if os.path.exists(FONT_FILE):
            plugin_font = ImageFont.truetype(FONT_FILE, font_size)
            server_api.log(f"SuperLobby: Loaded custom font '{os.path.basename(FONT_FILE)}'.")
        else:
            try:
                # Try to find a common system font as a better fallback.
                plugin_font = ImageFont.truetype("arialbd.ttf", font_size) # Arial Bold
                server_api.log("SuperLobby: Loaded system font 'Arial Bold'.")
            except IOError:
                plugin_font = ImageFont.load_default()
                server_api.log("SuperLobby: Custom/system fonts not found. Using default PIL font.")
    except Exception as e:
        plugin_font = ImageFont.load_default()
        server_api.log(f"SuperLobby: Error loading font: {e}. Using default.")

def load_admins_from_file(server_api):
    """
    Loads the admin list from the server's admins.json file.
    This allows the plugin to know who can use admin commands.
    """
    global ADMIN_USERS
    try:
        if os.path.exists(ADMIN_FILE_PATH):
            with open(ADMIN_FILE_PATH, 'r') as f:
                admins = json.load(f)
                if isinstance(admins, list):
                    ADMIN_USERS = set(admins)
                    server_api.log(f"SuperLobby: Successfully loaded {len(ADMIN_USERS)} admins.")
                else:
                    ADMIN_USERS = set()
                    server_api.log(f"SuperLobby: Warning - '{ADMIN_FILE_PATH}' is not a valid list.")
        else:
            ADMIN_USERS = set()
            server_api.log(f"SuperLobby: Warning - '{ADMIN_FILE_PATH}' not found. No admins loaded.")
    except Exception as e:
        ADMIN_USERS = set()
        server_api.log(f"SuperLobby: Error loading admins from '{ADMIN_FILE_PATH}': {e}")


async def generate_text_image(text, color_name="white"):
    """
    Generates a transparent PNG image with the given text and color, centered on a fixed-size canvas.
    The image is returned as a base64 data URL, ready to be sent to the client.
    """
    try:
        # Define a standard 16:9 canvas size, similar to the Zombies plugin.
        canvas_width, canvas_height = 854, 480

        # Map color names to RGB values.
        color_map = {
            "white": (255, 255, 255), "red": (255, 80, 80), "green": (80, 255, 80),
            "blue": (80, 80, 255), "yellow": (255, 255, 80), "orange": (255, 165, 0),
            "purple": (180, 80, 255), "pink": (255, 105, 180), "cyan": (0, 255, 255)
        }
        text_color = color_map.get(color_name.lower(), (255, 255, 255))
        shadow_color = (0, 0, 0, 180) # Semi-transparent black for shadow

        # Create the full-size transparent canvas.
        img = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Determine the size of the text to be drawn.
        text_bbox = draw.textbbox((0, 0), text, font=plugin_font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        # Calculate the centered position for the text.
        position_x = (canvas_width - text_width) / 2
        position_y = (canvas_height - text_height) / 2
        position = (position_x, position_y)

        # Draw shadow/outline slightly offset from the main text.
        shadow_offset = 5
        shadow_position = (position_x + shadow_offset, position_y + shadow_offset)
        draw.text(shadow_position, text, font=plugin_font, fill=shadow_color)

        # Draw the main text.
        draw.text(position, text, font=plugin_font, fill=text_color)

        # Convert the final image to a base64 data URL.
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        base64_data = base64.b64encode(buffer.read()).decode('utf-8')
        return f"data:image/png;base64,{base64_data}"

    except Exception as e:
        print(f"[SuperLobby] Error generating text image: {e}")
        traceback.print_exc()
        return None

# --- Background Tasks ---

async def periodic_broadcast_task(server_api):
    """
    A background task that periodically sends a configured message to all players.
    """
    while True:
        try:
            await asyncio.sleep(config["periodic_broadcast"]["interval_s"])
            if config["periodic_broadcast"]["enabled"] and config["periodic_broadcast"]["message"]:
                message = f"TELLRAW|PLACERSERVER|{config['periodic_broadcast']['message']}"
                await server_api.broadcast(message)
        except asyncio.CancelledError:
            server_api.log("SuperLobby: Periodic broadcast task stopped.")
            break
        except Exception as e:
            server_api.log(f"SuperLobby: Error in periodic broadcast task: {e}")
            # Wait a bit before retrying to avoid spamming logs on repeated errors
            await asyncio.sleep(60)

# --- Plugin Hooks ---

def on_load(server_api):
    """
    Called when the server loads the plugin. Initializes configuration and tasks.
    """
    global broadcast_task
    server_api.log("SuperLobby Plugin: Loading...")
    load_config(server_api)
    load_font(server_api)
    load_admins_from_file(server_api) # Load the admin list on startup
    # Start the periodic broadcast task if it's enabled
    if config["periodic_broadcast"]["enabled"]:
        broadcast_task = asyncio.create_task(periodic_broadcast_task(server_api))
    server_api.log("SuperLobby Plugin: Loaded successfully!")

def on_unload(server_api):
    """
    Called when the server unloads the plugin. Cleans up running tasks.
    """
    if broadcast_task and not broadcast_task.done():
        broadcast_task.cancel()
    server_api.log("SuperLobby Plugin: Unloaded.")

async def on_connect(websocket, server_api):
    """
    Called when a new player connects to the server.
    This now ONLY handles showing the welcome message image.
    """
    # Display the custom join message
    join_msg_config = config.get("join_message", {})
    text = join_msg_config.get("text")
    if text:
        color = join_msg_config.get("color", "white")
        duration = join_msg_config.get("duration_s", 5)
        
        # Generate the image and show it
        image_data_url = await generate_text_image(text, color)
        if image_data_url:
            await server_api.send_to_client(websocket, f"SHOW_IMAGE|PLACERSERVER|{image_data_url}")
            
            # Create a task to hide the image after the duration
            async def hide_image_later(api):
                await asyncio.sleep(duration)
                # This checks against the server's master list of connected clients.
                if websocket in api.get_connected_clients():
                    await api.send_to_client(websocket, "HIDE_IMAGE|PLACERSERVER|")
            
            asyncio.create_task(hide_image_later(server_api))


async def on_message(websocket, message_string, message_parts, server_api):
    """
    Called for every message received from a client.
    Handles all plugin commands, chat moderation, and the spawn teleport.
    """
    global players_awaiting_spawn

    # --- Event-Driven Spawn Teleport Logic ---
    # 1. Flag the player on their initial connection message.
    if len(message_parts) == 3 and message_parts[1] == "SYNC_REQ":
        if config.get("spawn_location"):
            username = message_parts[0]
            players_awaiting_spawn.add(username)

    # 2. Teleport the player upon receiving their first position update.
    if len(message_parts) >= 7 and message_parts[6] == "PLAYER_INFO":
        username = message_parts[0]
        # Check if this is the player we've been waiting for.
        if username in players_awaiting_spawn:
            loc = config["spawn_location"]
            if loc and loc.get("x") is not None and loc.get("y") is not None:
                teleport_msg = f"SET_POSITION|PLACERSERVER|{loc['x']}|{loc['y']}|{username}"
                await server_api.send_to_client(websocket, teleport_msg)
                server_api.log(f"SuperLobby: Teleported {username} to spawn.")
            # Remove them from the set so we don't teleport them again.
            players_awaiting_spawn.discard(username)
        
        # Also, cache their location for the !!set_spawn command.
        try:
            player_locations[username] = {"x": int(message_parts[1]), "y": int(message_parts[2])}
        except (ValueError, IndexError):
            pass # Ignore malformed PLAYER_INFO packets

    # --- Command and Chat Handling ---
    if len(message_parts) >= 4 and message_parts[0] == "PLAYER_MESSAGE" and message_parts[1] == "PLACERCLIENT":
        username = message_parts[2]
        content = "|".join(message_parts[3:])
        
        # --- Mute Check ---
        if username in config.get("muted_players", []):
            await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|You are muted.")
            return True # Returning True stops the message from being broadcast further

        # --- Command Parsing ---
        if content.startswith("!!"):
            command_line = content[2:].strip().split()
            command = command_line[0].lower() if command_line else ""
            
            # Check admin status using the plugin's own loaded admin list.
            is_admin = username in ADMIN_USERS

            # --- Admin Commands ---
            if is_admin:
                if command == "set_spawn":
                    if username in player_locations:
                        loc = player_locations[username]
                        config["spawn_location"] = loc
                        save_config(server_api)
                        await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|Server spawn set to your location: {loc['x']}, {loc['y']}")
                    else:
                        await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Your location is not yet known. Please move first.")
                    return True

                if command == "set_join_text":
                    # Example: !!set_join_text "Welcome Everyone!" yellow 7s
                    try:
                        # Re-join text in quotes
                        full_text = ""
                        text_end_index = -1
                        if '"' in content:
                            start_index = content.find('"') + 1
                            end_index = content.rfind('"') # Use rfind to get the last quote
                            if end_index > start_index:
                                full_text = content[start_index:end_index]
                                text_end_index = end_index
                        
                        if not full_text:
                             raise ValueError("Text must be in quotes.")

                        remaining_args = content[text_end_index+1:].strip().split()
                        color = remaining_args[0] if remaining_args else "white"
                        duration_str = remaining_args[1] if len(remaining_args) > 1 else "5s"
                        duration = int(duration_str.replace('s', ''))

                        config["join_message"] = {"text": full_text, "color": color, "duration_s": duration}
                        save_config(server_api)
                        await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|Join message updated successfully.")
                    except Exception as e:
                        await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|Usage: !!set_join_text \"Your Text\" <color> <duration>s")
                        server_api.log(f"SuperLobby: Error parsing set_join_text: {e}")
                    return True
                
                if command == "reload_admins":
                    load_admins_from_file(server_api)
                    await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|Admin list reloaded. Found {len(ADMIN_USERS)} admins.")
                    return True

                if command == "set_rules":
                    try:
                        sub_command = command_line[1]
                        if sub_command == "add":
                            rule_text = " ".join(command_line[2:])
                            config["server_rules"].append(rule_text)
                            save_config(server_api)
                            await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|Rule added.")
                        elif sub_command == "clear":
                            config["server_rules"] = []
                            save_config(server_api)
                            await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|All rules cleared.")
                    except IndexError:
                         await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|Usage: !!set_rules <add/clear> [text]")
                    return True
                
                if command == "mute":
                    try:
                        player_to_mute = command_line[1]
                        if player_to_mute not in config["muted_players"]:
                            config["muted_players"].append(player_to_mute)
                            save_config(server_api)
                            await server_api.broadcast(f"TELLRAW|PLACERSERVER|{player_to_mute} has been muted.")
                        else:
                            await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|{player_to_mute} is already muted.")
                    except IndexError:
                        await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|Usage: !!mute <username>")
                    return True

                if command == "unmute":
                    try:
                        player_to_unmute = command_line[1]
                        if player_to_unmute in config["muted_players"]:
                            config["muted_players"].remove(player_to_unmute)
                            save_config(server_api)
                            await server_api.broadcast(f"TELLRAW|PLACERSERVER|{player_to_unmute} has been unmuted.")
                        else:
                            await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|{player_to_unmute} is not muted.")
                    except IndexError:
                        await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|Usage: !!unmute <username>")
                    return True

            # --- Public Commands ---
            if command == "rules":
                rules = config.get("server_rules", [])
                if rules:
                    await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|--- Server Rules ---")
                    for rule in rules:
                        await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|{rule}")
                        await asyncio.sleep(0.1) # Small delay to prevent message flood
                else:
                    await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|No server rules have been set.")
                return True
            
    return False # Let other plugins or the server handle the message

async def on_disconnect(websocket, server_api):
    """
    Called when a player disconnects. Cleans up cached data.
    """
    global players_awaiting_spawn
    username = server_api.get_username_from_websocket(websocket)
    if username:
        if username in player_locations:
            del player_locations[username]
        # Clean up the player from the spawn set if they disconnect before being teleported.
        players_awaiting_spawn.discard(username)
