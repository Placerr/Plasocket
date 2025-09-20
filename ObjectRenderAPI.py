import asyncio
import json
import os
import inspect

# --- Plugin Configuration ---
PLUGIN_FOLDER = "plugins/ObjectRenderAPI"
DATA_FOLDER = os.path.join(PLUGIN_FOLDER, "data")
PIXEL_SIZE = 10 # This now acts as the default grid cell size for positioning calculations

# --- Global State ---
API_INSTANCE = None
player_locations = {}
IS_CORE_PLUGIN = True 
PLUGINS_AWAITING_API = []

class ObjectRenderAPI:
    def __init__(self, server_api):
        self.server_api = server_api
        self.rendered_objects = {}
        self.next_object_id = 10000
        self.models_cache = {}
        self.last_rendered_states = {}

    def _get_caller_plugin_name(self):
        try:
            # Go up 3 frames to find the original caller outside this API module
            caller_frame = inspect.stack()[3]
            filename = os.path.basename(caller_frame.filename)
            plugin_name, _ = os.path.splitext(filename)
            return plugin_name
        except IndexError:
            return "unknown"

    async def __clear_internal(self, username: str, plugin_name: str, targets: list = None):
        if username in self.rendered_objects and plugin_name in self.rendered_objects[username]:
            ids_to_remove = [obj['id'] for obj in self.rendered_objects[username].pop(plugin_name)]
            if username in self.last_rendered_states and plugin_name in self.last_rendered_states[username]:
                self.last_rendered_states[username].pop(plugin_name)
            
            websockets = [self.server_api.get_websocket_from_username(t) for t in targets or [] if self.server_api.get_websocket_from_username(t)]
            tasks = []
            for obj_id in ids_to_remove:
                message = f"OBJECT_DESTROY|PLACERSERVER|{obj_id}"
                if targets and websockets:
                    tasks.extend([ws.send(message) for ws in websockets])
                else:
                    # If no specific targets, broadcast to everyone
                    tasks.append(self.server_api.broadcast(message))
            
            if tasks: await asyncio.gather(*tasks)
            return True
        return False

    async def clear_rendered_object(self, username: str, targets: list = None):
        plugin_name = self._get_caller_plugin_name()
        await self.__clear_internal(username, plugin_name, targets)

    async def _render_object(self, username: str, plugin_name: str, model_data: dict, targets: list = None):
        """Core rendering logic that takes model data as a dictionary."""
        if username not in player_locations: return
        player_state = player_locations.get(username, {});
        if not player_state or not model_data: return

        base_pos = {"x": player_state["x"], "y": player_state["y"]}
        direction = player_state.get("direction", 0)
        
        is_update = username in self.rendered_objects and plugin_name in self.rendered_objects[username]

        current_state = {'x': base_pos['x'], 'y': base_pos['y'], 'direction': direction}
        last_state = self.last_rendered_states.get(username, {}).get(plugin_name)
        
        if is_update and last_state and last_state == current_state:
            return # No change in player state, no need to re-render

        pixels = model_data.get("pixels", [])
        grid_height = model_data.get("grid_height", 16)
        grid_width = model_data.get("grid_width", 16)
        default_pixel_size = model_data.get("default_pixel_size", PIXEL_SIZE)
        if not pixels: return

        websockets = [self.server_api.get_websocket_from_username(t) for t in targets or [] if self.server_api.get_websocket_from_username(t)]

        if is_update:
            existing_objects = self.rendered_objects[username][plugin_name]
            tasks = []
            for i, pixel in enumerate(pixels):
                if i >= len(existing_objects): break # Safety check
                obj_id = existing_objects[i]['id']
                
                pixel_grid_x = pixel['x']
                if direction == 1:
                    pixel_grid_x = (grid_width - 1) - pixel_grid_x

                p_width = pixel.get('width', default_pixel_size)
                p_height = pixel.get('height', default_pixel_size)
                p_top = pixel.get('top', 0)
                p_left = pixel.get('left', 0)

                world_x = base_pos['x'] + (pixel_grid_x * PIXEL_SIZE) + p_left
                world_y = (base_pos['y'] - grid_height * PIXEL_SIZE) + (pixel['y'] * PIXEL_SIZE) + p_top
                
                payload = f"{pixel['color_index']}|{int(world_x)}|{int(world_y)}|{int(p_width)}|{int(p_height)}|{obj_id}"
                message = f"OBJECT_MODIFY|PLACERSERVER|{payload}"
                if targets and websockets:
                    tasks.extend([ws.send(message) for ws in websockets])
                else:
                    tasks.append(self.server_api.broadcast(message))
            if tasks: await asyncio.gather(*tasks)
        else: # Create new objects
            await self.__clear_internal(username, plugin_name, targets)
            rendered_objects_list = []
            create_tasks = []
            for pixel in pixels:
                obj_id = self.next_object_id; self.next_object_id += 1
                
                pixel_grid_x = pixel['x']
                if direction == 1:
                    pixel_grid_x = (grid_width - 1) - pixel_grid_x
                
                p_width = pixel.get('width', default_pixel_size)
                p_height = pixel.get('height', default_pixel_size)
                p_top = pixel.get('top', 0)
                p_left = pixel.get('left', 0)

                world_x = base_pos['x'] + (pixel_grid_x * PIXEL_SIZE) + p_left
                world_y = (base_pos['y'] - grid_height * PIXEL_SIZE) + (pixel['y'] * PIXEL_SIZE) + p_top

                payload = f"{pixel['color_index']}|{int(world_x)}|{int(world_y)}|{int(p_width)}|{int(p_height)}|{obj_id}"
                message = f"OBJECT|PLACERSERVER|{payload}"
                if targets and websockets:
                    create_tasks.extend([ws.send(message) for ws in websockets])
                else:
                    create_tasks.append(self.server_api.broadcast(message))
                rendered_objects_list.append({'id': obj_id})
            
            if create_tasks: await asyncio.gather(*create_tasks)
            
            if username not in self.rendered_objects: self.rendered_objects[username] = {}
            self.rendered_objects[username][plugin_name] = rendered_objects_list

        if username not in self.last_rendered_states: self.last_rendered_states[username] = {}
        self.last_rendered_states[username][plugin_name] = current_state

    async def render_object_from_file(self, username: str, object_name: str, targets: list = None):
        """Loads a model from a .json file and renders it attached to a player."""
        plugin_name = self._get_caller_plugin_name()
        
        if object_name not in self.models_cache:
            file_path = os.path.join(DATA_FOLDER, f"{object_name}.json")
            if not os.path.exists(file_path):
                self.server_api.log(f"ObjectRenderAPI Error: Model file '{object_name}.json' not found.")
                return
            try:
                with open(file_path, 'r') as f:
                    self.models_cache[object_name] = json.load(f)
            except Exception as e:
                self.server_api.log(f"Error loading model {object_name}: {e}")
                return
        
        model_data = self.models_cache.get(object_name)
        if model_data:
            await self._render_object(username, plugin_name, model_data, targets)

    async def render_object_from_data(self, username: str, model_data: dict, targets: list = None):
        """Renders an object attached to a player directly from a dictionary."""
        plugin_name = self._get_caller_plugin_name()
        if isinstance(model_data, dict):
            await self._render_object(username, plugin_name, model_data, targets)
        else:
            self.server_api.log(f"ObjectRenderAPI Error from {plugin_name}: model_data must be a dictionary.")

def on_load(server_api):
    global API_INSTANCE
    server_api.log("ObjectRenderAPI: Loading...")
    if not os.path.exists(PLUGIN_FOLDER): os.makedirs(PLUGIN_FOLDER)
    if not os.path.exists(DATA_FOLDER): os.makedirs(DATA_FOLDER)
    API_INSTANCE = ObjectRenderAPI(server_api)
    server_api.log("ObjectRenderAPI: Service is now available to other plugins.")
    for plugin_module in PLUGINS_AWAITING_API:
        if hasattr(plugin_module, "on_api_ready"):
            try: asyncio.create_task(plugin_module.on_api_ready(server_api))
            except Exception as e: server_api.log(f"ObjectRenderAPI: Error notifying '{plugin_module.__name__}': {e}")
    PLUGINS_AWAITING_API.clear()

async def on_message(websocket, message_string, message_parts, server_api):
    if len(message_parts) >= 7 and message_parts[6] == "PLAYER_INFO":
        username = message_parts[0]
        try:
            state = player_locations.get(username, {})
            state['x'], state['y'] = int(message_parts[1]), int(message_parts[2])
            if len(message_parts) > 4: state['direction'] = int(message_parts[4])
            player_locations[username] = state
        except (ValueError, IndexError): pass
    return False

async def on_disconnect(websocket, server_api):
    username = server_api.get_username_from_websocket(websocket)
    if username and API_INSTANCE:
        user_plugins = list(API_INSTANCE.rendered_objects.get(username, {}).keys())
        for plugin_name in user_plugins:
            await API_INSTANCE.__clear_internal(username, plugin_name)
        
        player_locations.pop(username, None)
        API_INSTANCE.last_rendered_states.pop(username, None)

def on_unload(server_api):
    server_api.log("ObjectRenderAPI: Unloaded.")
