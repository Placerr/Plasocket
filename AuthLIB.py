import asyncio
import json
import os

# --- Plugin State ---
# This will store registered users: {username: password_hash}
# For simplicity, we'll store plaintext passwords in a JSON file.
# In a real application, you'd use proper password hashing (e.g., bcrypt).
USER_DB_FILE = "plugins/users.json"
REGISTERED_USERS = {}

# Stores the authentication status for each client (websocket -> boolean)
# True if the client has successfully authenticated
g_authenticated_clients = {}

# Path to the specific world file to send during login/registration
LOGIN_WORLD_FILE_PATH = "worlds/login.pw"

# --- Utility Functions ---
def _load_users():
    """Loads registered users from the JSON file."""
    global REGISTERED_USERS
    if os.path.exists(USER_DB_FILE):
        try:
            with open(USER_DB_FILE, 'r') as f:
                REGISTERED_USERS = json.load(f)
            print(f"PasswordAuthPlugin: Loaded {len(REGISTERED_USERS)} users from {USER_DB_FILE}")
        except json.JSONDecodeError:
            print(f"PasswordAuthPlugin: Error decoding {USER_DB_FILE}. Starting with empty user database.")
            REGISTERED_USERS = {}
    else:
        print(f"PasswordAuthPlugin: {USER_DB_FILE} not found. Starting with empty user database.")
        REGISTERED_USERS = {}

def _save_users():
    """Saves registered users to the JSON file."""
    try:
        with open(USER_DB_FILE, 'w') as f:
            json.dump(REGISTERED_USERS, f, indent=4)
        print(f"PasswordAuthPlugin: Saved {len(REGISTERED_USERS)} users to {USER_DB_FILE}")
    except IOError as e:
        print(f"PasswordAuthPlugin: Error saving users to {USER_DB_FILE}: {e}")

# --- Plugin Hooks ---

def on_load(server_api):
    server_api.log("PasswordAuthPlugin: Initializing...")
    _load_users()
    server_api.log("PasswordAuthPlugin: Ready.")

async def on_connect(websocket, server_api):
    server_api.log(f"PasswordAuthPlugin: Client {websocket.remote_address} connected.")
    # Initialize authentication status to False for new clients
    g_authenticated_clients[websocket] = False
    
    # The initial sync request handling logic is in on_message.

async def on_disconnect(websocket, server_api):
    server_api.log(f"PasswordAuthPlugin: Client {websocket.remote_address} disconnected.")
    # Clean up authentication status
    if websocket in g_authenticated_clients:
        del g_authenticated_clients[websocket]
    # Also clean up temporary username if it exists
    if hasattr(websocket, 'username_for_auth'):
        del websocket.username_for_auth

async def _send_password_prompt_loop(websocket, server_api):
    """Sends repeated password prompts until authenticated or disconnected."""
    try:
        while not g_authenticated_clients.get(websocket, False):
            username = getattr(websocket, 'username_for_auth', None)
            prompt_message = "Send your Password to Register." # Default for new user
            
            # Determine if it's a login or register prompt based on existing users
            if username and username in REGISTERED_USERS:
                prompt_message = "Send your Password to Login."
            
            await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|{prompt_message}")
            await asyncio.sleep(3)
    except asyncio.CancelledError:
        server_api.log(f"PasswordAuthPlugin: Password prompt loop for {websocket.remote_address} cancelled.")
    except Exception as e:
        server_api.log(f"PasswordAuthPlugin: Error in password prompt loop for {websocket.remote_address}: {e}")


async def on_message(websocket, message_string, message_parts, server_api):
    """
    Handles incoming messages for the password authentication plugin.
    """
    
    # Check if the client is already authenticated. If so, handle specific commands or pass to main server.
    if g_authenticated_clients.get(websocket, False):
        # Handle !authlib command for authenticated users
        if len(message_parts) == 4 and \
           message_parts[0] == "PLAYER_MESSAGE" and \
           message_parts[1] == "PLACERCLIENT" and \
           message_parts[3].lower() == "!authlib":
            
            await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|AuthLIB for Plasocket 0.2.0 - Youre Logged in!")
            server_api.log(f"PasswordAuthPlugin: Sent !authlib response to {websocket.remote_address}.")
            return True # Message handled by plugin

        # Only log if the message content does not contain specific keywords like PLAYER_INFO, PLACE, ERASE
        if not any(keyword in message_string for keyword in ["PLAYER_INFO", "PLACERSERVER", "PLACERCLIENT", "PLACE", "ERASE", "DAMAGE"]):
            server_api.log(f"PasswordAuthPlugin: Authenticated client {websocket.remote_address} sent: {message_string} (passing to main server).")
        return False # Let the main server handler process messages from authenticated clients

    # --- Handle SYNC_REQ when not authenticated ---
    # Expected: USERNAME|SYNC_REQ|VERSION (3 parts in total for the main server)
    # The plugin only cares about the SYNC_REQ type here.
    if len(message_parts) >= 2 and message_parts[1] == "SYNC_REQ":
        username = message_parts[0]
        server_api.log(f"PasswordAuthPlugin: SYNC_REQ from {username} ({websocket.remote_address}). Awaiting password.")
        
        # Store username temporarily with websocket for password check
        websocket.username_for_auth = username 

        # --- Send LOGIN_WORLD_FILE_PATH content ---
        login_world_content = ""
        if os.path.exists(LOGIN_WORLD_FILE_PATH):
            try:
                with open(LOGIN_WORLD_FILE_PATH, 'r') as f:
                    login_world_content = f.read()
                server_api.log(f"PasswordAuthPlugin: Loaded {LOGIN_WORLD_FILE_PATH} for {username}.")
            except Exception as e:
                server_api.log(f"PasswordAuthPlugin: Error reading {LOGIN_WORLD_FILE_PATH}: {e}. Sending empty world data.")
                login_world_content = "" # Fallback to empty if reading fails
        else:
            server_api.log(f"PasswordAuthPlugin: {LOGIN_WORLD_FILE_PATH} not found. Sending empty world data for login.")
            login_world_content = "" # Send empty if file doesn't exist

        await server_api.send_to_client(websocket, f"WORLD_DATA|PLACERSERVER|{login_world_content}")
        await server_api.send_to_client(websocket, "SET_POSITION|PLACERSERVER|100|100")
        
        # Start a background task to repeatedly send the password prompt
        asyncio.create_task(_send_password_prompt_loop(websocket, server_api))
        
        return True # This plugin handled the SYNC_REQ initially, preventing main server processing.

    # --- Handle PLAYER_MESSAGE (password submission) ONLY if not authenticated ---
    # Expected: PLAYER_MESSAGE|PLACERCLIENT|USERNAME|MESSAGE_CONTENT
    if len(message_parts) == 4 and \
       message_parts[0] == "PLAYER_MESSAGE" and \
       message_parts[1] == "PLACERCLIENT":
        
        username = message_parts[2]
        password = message_parts[3]
        
        # Ensure this message is from the client that sent the SYNC_REQ we are waiting for
        if not hasattr(websocket, 'username_for_auth') or websocket.username_for_auth != username:
            server_api.log(f"PasswordAuthPlugin: Received password from {username} but no pending SYNC_REQ or mismatched user. Ignoring.")
            # For security, if it's a PLAYER_MESSAGE from an unauthenticated client,
            # we should still prevent it from being broadcasted by the main server.
            await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Error: Please send your password after SYNC_REQ.")
            return True # Handled by plugin (preventing broadcast), but it's an invalid password attempt flow.

        server_api.log(f"PasswordAuthPlugin: Received password attempt from {username} ({websocket.remote_address}).")

        # --- Authentication Logic ---
        if username in REGISTERED_USERS:
            # Existing user - attempt login
            if REGISTERED_USERS[username] == password: # In a real app, hash and compare
                server_api.log(f"PasswordAuthPlugin: {username} authenticated successfully!")
                # Proceed to send main world data (same as registration success)
            else:
                server_api.log(f"PasswordAuthPlugin: Incorrect password for {username}.")
                await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Incorrect password. Try again.")
                return True # Handled, but failed login (stay on login screen and prevent main server processing)
        else:
            # New user - register
            REGISTERED_USERS[username] = password # In a real app, hash the password
            _save_users()
            server_api.log(f"PasswordAuthPlugin: Registered new user: {username}.")
            # No kick here, proceed to authenticate and send main world
        
        # --- Common logic for successful login OR successful registration ---
        g_authenticated_clients[websocket] = True
        await server_api.send_to_client(websocket, "JOIN_ACCEPT|PLACERSERVER|ME")
        
        # Load and send actual world data (from the main server's configured path)
        # Assuming the main server's world is in "worlds/world.pw"
        MAIN_WORLD_FILE_PATH = "worlds/world.pw" 
        try:
            if not os.path.exists(MAIN_WORLD_FILE_PATH):
                await server_api.send_to_client(websocket, f"ERROR|SERVER|{MAIN_WORLD_FILE_PATH} not found")
                server_api.log(f"PasswordAuthPlugin: {MAIN_WORLD_FILE_PATH} not found for {username}.")
            else:
                with open(MAIN_WORLD_FILE_PATH, 'r') as f: world_content = f.read()
                await server_api.send_to_client(websocket, f"WORLD_DATA|PLACERSERVER|{world_content}")
                server_api.log(f"PasswordAuthPlugin: Main WORLD_DATA sent to {username}.")
        except Exception as e:
            await server_api.send_to_client(websocket, f"ERROR|SERVER|Error sending main world data: {e}")
            server_api.log(f"PasswordAuthPlugin: Error sending main world data to {username}: {e}")

        # After successful authentication/registration, remove the temporary username attribute
        del websocket.username_for_auth 
        return True # Handled authentication/registration, preventing main server processing.

    # --- If client is not authenticated and sent any other message type ---
    # This block will catch any message that is NOT a SYNC_REQ or a PLAYER_MESSAGE
    # from an unauthenticated client.
    server_api.log(f"PasswordAuthPlugin: Unauthenticated client {websocket.remote_address} sent unaccepted message: {message_string}. Informing client.")
    await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Error: Please send your password or SYNC_REQ.")
    return True # Message handled (by informing the client and preventing main server processing/broadcasting).
