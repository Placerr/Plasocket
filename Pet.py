import asyncio
import json
import os
import math
import traceback
import sys

# --- Plugin Dependencies ---
try:
    # Use a direct, top-level import. This will find the module
    # instance loaded by the server into sys.modules.
    import ObjectRenderAPI as ObjectRenderAPI_Module
except ImportError:
    ObjectRenderAPI_Module = None

# --- Plugin Configuration ---
PLUGIN_FOLDER = "plugins/PetPlugin"

# --- Pet Behavior Constants ---
PET_SPEED = 0.08
FOLLOW_DISTANCE = 120
MAX_SPEED = 15.0
TELEPORT_THRESHOLD = 1200
UPDATE_INTERVAL = 1 / 20

# --- Global State ---
active_pets = {}
player_locations = {}
pet_update_task = None
is_plugin_initialized = False # Prevents running setup logic multiple times

# --- MODIFIED: Added "pixel_size" to the model data ---
DOG_MODEL_DATA = {
    "name": "dog", "width": 16, "height": 16, "pixel_size": 12,
    "pixels": [
        {"x": 6, "y": 4, "color_index": 9}, {"x": 8, "y": 4, "color_index": 9},
        {"x": 6, "y": 5, "color_index": 9}, {"x": 7, "y": 5, "color_index": 9},
        {"x": 8, "y": 5, "color_index": 9}, {"x": 6, "y": 6, "color_index": 0},
        {"x": 7, "y": 6, "color_index": 9}, {"x": 8, "y": 6, "color_index": 0},
        {"x": 2, "y": 7, "color_index": 9}, {"x": 6, "y": 7, "color_index": 9},
        {"x": 7, "y": 7, "color_index": 1}, {"x": 8, "y": 7, "color_index": 9},
        {"x": 2, "y": 8, "color_index": 9}, {"x": 3, "y": 8, "color_index": 9},
        {"x": 4, "y": 8, "color_index": 9}, {"x": 5, "y": 8, "color_index": 9},
        {"x": 6, "y": 8, "color_index": 9}, {"x": 7, "y": 8, "color_index": 9},
        {"x": 8, "y": 8, "color_index": 9}, {"x": 2, "y": 9, "color_index": 9},
        {"x": 3, "y": 9, "color_index": 9}, {"x": 4, "y": 9, "color_index": 9},
        {"x": 5, "y": 9, "color_index": 9}, {"x": 6, "y": 9, "color_index": 9},
        {"x": 7, "y": 9, "color_index": 9}, {"x": 8, "y": 9, "color_index": 9},
        {"x": 2, "y": 10, "color_index": 9}, {"x": 6, "y": 10, "color_index": 9},
        {"x": 8, "y": 10, "color_index": 9}
    ]
}

class Pet:
    def __init__(self, owner_username, start_pos):
        self.owner = owner_username
        self.pos = {'x': float(start_pos['x']), 'y': float(start_pos['y'])}
        self.vel = {'x': 0.0, 'y': 0.0}
        self.facing_direction = 0
        self.render_anchor_name = f"_pet_anchor_{self.owner}"

    def update(self, player_pos):
        player_x, player_y = float(player_pos['x']), float(player_pos['y'])
        dx = player_x - self.pos['x']
        dy = player_y - self.pos['y']
        
        distance_2d = math.sqrt(dx**2 + dy**2)

        if distance_2d > TELEPORT_THRESHOLD:
            self.pos = {'x': player_x - FOLLOW_DISTANCE, 'y': player_y}
            self.vel = {'x': 0, 'y': 0}
            return

        horizontal_distance = abs(dx)
        if horizontal_distance > FOLLOW_DISTANCE:
            self.vel['x'] += dx * PET_SPEED
        else:
            self.vel['x'] *= 0.85 

        speed = abs(self.vel['x'])
        if speed > MAX_SPEED:
            scale = MAX_SPEED / speed
            self.vel['x'] *= scale
        
        self.vel['y'] = 0

        self.pos['x'] += self.vel['x']
        self.pos['y'] = player_y

        if self.vel['x'] > 0.5:
            self.facing_direction = 0
        elif self.vel['x'] < -0.5:
            self.facing_direction = 1
    
    async def render(self):
        api_instance = getattr(ObjectRenderAPI_Module, 'API_INSTANCE', None)
        if not api_instance: return

        ObjectRenderAPI_Module.player_locations[self.render_anchor_name] = {
            'x': self.pos['x'], 'y': self.pos['y'], 'direction': self.facing_direction
        }
        await api_instance.render_object_from_file(self.render_anchor_name, 'dog', targets=[self.owner])


    async def despawn(self):
        api_instance = getattr(ObjectRenderAPI_Module, 'API_INSTANCE', None)
        if api_instance:
            await api_instance.clear_rendered_object(self.render_anchor_name, targets=[self.owner])

async def pet_update_loop():
    while True:
        try:
            for pet in list(active_pets.values()):
                owner_pos = player_locations.get(pet.owner)
                if owner_pos:
                    pet.update(owner_pos)
                    await pet.render()
            await asyncio.sleep(UPDATE_INTERVAL)
        except asyncio.CancelledError: break
        except Exception as e:
            print(f"[PetPlugin] CRITICAL ERROR in update loop: {e}")
            traceback.print_exc()
            await asyncio.sleep(5)

async def initialize_plugin(server_api):
    global pet_update_task, is_plugin_initialized
    if is_plugin_initialized: return
    
    try:
        api_data_folder = os.path.join("plugins", "ObjectRenderAPI", "data")
        if not os.path.exists(api_data_folder): os.makedirs(api_data_folder)
        
        dog_model_path = os.path.join(api_data_folder, "dog.json")
        if not os.path.exists(dog_model_path):
            with open(dog_model_path, 'w') as f:
                json.dump(DOG_MODEL_DATA, f, indent=2)
            server_api.log("PetPlugin: Automatically installed 'dog.json' model.")
    except Exception as e:
        server_api.log(f"PetPlugin: WARNING - Could not auto-install dog model: {e}")

    if not os.path.exists(PLUGIN_FOLDER): os.makedirs(PLUGIN_FOLDER)

    if pet_update_task and not pet_update_task.done(): pet_update_task.cancel()
    pet_update_task = asyncio.create_task(pet_update_loop())
    is_plugin_initialized = True
    server_api.log("PetPlugin: Initialized successfully and update loop started.")

def on_load(server_api):
    server_api.log("PetPlugin: Loading...")
    
    global ObjectRenderAPI_Module
    if ObjectRenderAPI_Module is None:
        try:
            import ObjectRenderAPI as ObjectRenderAPI_Module
        except ImportError:
            server_api.log("PetPlugin: FATAL - Could not find ObjectRenderAPI. Plugin will be disabled.")
            return

    if getattr(ObjectRenderAPI_Module, 'API_INSTANCE', None):
        server_api.log("PetPlugin: ObjectRenderAPI found immediately. Initializing...")
        asyncio.create_task(initialize_plugin(server_api))
    elif hasattr(ObjectRenderAPI_Module, 'PLUGINS_AWAITING_API'):
        server_api.log("PetPlugin: ObjectRenderAPI not ready yet. Registering for callback...")
        this_plugin_module = sys.modules[__name__]
        ObjectRenderAPI_Module.PLUGINS_AWAITING_API.append(this_plugin_module)
    else:
        server_api.log("PetPlugin: FATAL - Could not find a way to register with ObjectRenderAPI. Plugin will be disabled.")


async def on_api_ready(server_api):
    server_api.log("PetPlugin: Received 'on_api_ready' signal. Initializing...")
    await initialize_plugin(server_api)

async def on_unload(server_api):
    if pet_update_task and not pet_update_task.done(): pet_update_task.cancel()
    for pet in list(active_pets.values()): await pet.despawn()
    active_pets.clear()
    global is_plugin_initialized
    is_plugin_initialized = False
    server_api.log("PetPlugin: Unloaded and all pets despawned.")

async def on_message(websocket, message_string, message_parts, server_api):
    if not is_plugin_initialized: return False
    username = server_api.get_username_from_websocket(websocket)
    if not username: return False

    if len(message_parts) >= 7 and message_parts[6] == "PLAYER_INFO":
        p_name = message_parts[0]
        try:
            player_locations[p_name] = { "x": int(message_parts[1]), "y": int(message_parts[2]) }
        except (ValueError, IndexError): pass

    if len(message_parts) >= 4 and message_parts[0] == "PLAYER_MESSAGE" and message_parts[1] == "PLACERCLIENT":
        sender = message_parts[2]
        command = message_parts[3].strip().lower()

        if sender == username and command == "!pet":
            if username in active_pets:
                await active_pets.pop(username).despawn()
                await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Your pet has been dismissed.")
            else:
                if username in player_locations:
                    active_pets[username] = Pet(username, player_locations[username])
                    await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|A furry friend has appeared!")
                else:
                    await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Cannot spawn pet, your location is unknown. Please move first.")
            return True
    return False

async def on_disconnect(websocket, server_api):
    if not is_plugin_initialized: return
    username = server_api.get_username_from_websocket(websocket)
    if username and username in active_pets:
        await active_pets.pop(username).despawn()
        print(f"[PetPlugin] Cleaned up pet for disconnected user: {username}")

