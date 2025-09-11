import asyncio
import json
import os
import random
import functools
import traceback
import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

# --- Plugin Configuration ---
PLUGIN_FOLDER = "plugins/RedLightGreenLight"
CONFIG_FILE = os.path.join(PLUGIN_FOLDER, "config.json")
NPC_FILE = os.path.join(PLUGIN_FOLDER, "npc_location.json")
STATS_FILE = os.path.join(PLUGIN_FOLDER, "player_stats.json")
FONT_FILE = os.path.join(PLUGIN_FOLDER, "font.ttf") 
END_GAME_FONT_FILE = os.path.join(PLUGIN_FOLDER, "arial_black.ttf")

# --- Constants ---
TILE_SIZE = 40
BLOCK_IDS = { "AIR": -1, "STONE": 2, "BRICK": 7, "GOLD": 15, "GRASS": 1, "DIAMOND": 12 }

# --- Default Configuration ---
DEFAULT_CONFIG = {
    "min_players": 1,
    "max_players": 12,
    "countdown_normal": 45,
    "game_duration_seconds": 120,
    "min_green_light_seconds": 3,
    "max_green_light_seconds": 7,
    "min_red_light_seconds": 2,
    "max_red_light_seconds": 5,
    "lobby_location": {"x": 500, "y": 1100}
}

# --- Global State ---
config = {}
active_games = {}
player_to_game = {}
next_game_id = 0
player_locations = {}
npc_location = {}
player_stats = {}
global_broadcast_task = None
last_npc_name = ""
font, font_scaled, end_game_font = None, None, None

# --- Image Generation ---
async def generate_flash_image(color):
    try:
        img = Image.new('RGBA', (854, 480), color)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('utf-8')}"
    except Exception:
        return None

async def generate_and_broadcast_light_image(game_instance, light_state):
    try:
        text = "GREEN LIGHT" if light_state == "green" else "RED LIGHT"
        color = (80, 255, 80, 255) if light_state == "green" else (255, 80, 80, 255)
        
        img = Image.new('RGBA', (854, 480), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        text_bbox = draw.textbbox((0, 0), text, font=end_game_font)
        text_width, text_height = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
        pos = ((854 - text_width) / 2, 50)
        
        draw.text((pos[0] + 5, pos[1] + 5), text, font=end_game_font, fill=(0, 0, 0, 128))
        draw.text(pos, text, font=end_game_font, fill=color)
        
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        data_url = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('utf-8')}"
        await game_instance.broadcast_to_game_players(f"SHOW_IMAGE|PLACERSERVER|{data_url}")
    except Exception as e:
        game_instance.server_api.log(f"RLGL_Image: Error generating light image: {e}")

async def generate_end_game_image(game_instance, winner):
    try:
        text = f"{winner} Wins!" if winner else "Time's Up!"
        color = (255, 215, 0, 255) if winner else (200, 200, 200, 255)
        
        img = Image.new('RGBA', (854, 480), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        text_bbox = draw.textbbox((0, 0), text, font=end_game_font)
        text_width, text_height = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
        pos = ((854 - text_width) / 2, (480 - text_height) / 2)

        draw.text((pos[0] + 5, pos[1] + 5), text, font=end_game_font, fill=(0, 0, 0, 128))
        draw.text(pos, text, font=end_game_font, fill=color)
        
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        data_url = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('utf-8')}"
        await game_instance.broadcast_to_game_players(f"SHOW_IMAGE|PLACERSERVER|{data_url}")
    except Exception as e:
        game_instance.server_api.log(f"RLGL_Image: Error generating end game image: {e}")

# --- Utility Functions ---
def load_all():
    global config, npc_location, player_stats, font, font_scaled, end_game_font
    if not os.path.exists(PLUGIN_FOLDER): os.makedirs(PLUGIN_FOLDER)
    
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f: config = json.load(f)
    else: config = DEFAULT_CONFIG.copy()
    for key, value in DEFAULT_CONFIG.items(): config.setdefault(key, value)
    with open(CONFIG_FILE, 'w') as f: json.dump(config, f, indent=4)

    if os.path.exists(NPC_FILE):
        with open(NPC_FILE, 'r') as f: npc_location = json.load(f)
    
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r') as f: player_stats = json.load(f)
    else: player_stats = {}

    try:
        font = ImageFont.truetype(FONT_FILE, 24) if os.path.exists(FONT_FILE) else ImageFont.truetype("arial.ttf", 24)
        font_scaled = ImageFont.truetype(FONT_FILE, 48) if os.path.exists(FONT_FILE) else ImageFont.truetype("arial.ttf", 48)
        end_game_font = ImageFont.truetype(END_GAME_FONT_FILE, 80) if os.path.exists(END_GAME_FONT_FILE) else ImageFont.truetype("arialbd.ttf", 80)
    except IOError:
        font, font_scaled, end_game_font = (ImageFont.load_default(),)*3

def save_stats():
    with open(STATS_FILE, 'w') as f: json.dump(player_stats, f, indent=4)

def update_player_stat(username, stat, value):
    stats = player_stats.setdefault(username, {"wins": 0})
    stats[stat] = stats.get(stat, 0) + value
    save_stats()

def rle_encode(grid):
    width, height = len(grid[0]), len(grid)
    parts = []; current_id = None; count = 0
    for y in range(height):
        for x in range(width):
            block_id = grid[y][x]
            if current_id is None: current_id, count = block_id, 1
            elif block_id == current_id: count += 1
            else:
                parts.append(f"{count}x{current_id}" if count > 1 else str(current_id)); current_id, count = block_id, 1
    if current_id is not None: parts.append(f"{count}x{current_id}" if count > 1 else str(current_id))
    return ",".join(parts)

# --- Game Instance Class ---
class GameInstance:
    def __init__(self, game_id, server_api):
        self.game_id = game_id
        self.server_api = server_api
        self.game_state = "waiting"
        self.players = set()
        self.in_game_players = set()
        self.eliminated_players = set()
        self.player_last_positions = {}
        self.light_state = "green"
        self.doll_npc_id = self.game_id * 1000
        self.doll_facing_direction = 1 # 0=right, 1=left
        self.world_data_cache = {}
        self.tasks = []

    def generate_world(self, world_type):
        if world_type in self.world_data_cache: return self.world_data_cache[world_type]
        
        if world_type == "lobby":
            w, h = 40, 30; grid = [[-1]*w for _ in range(h)]
            for x in range(w): grid[h-5][x] = BLOCK_IDS["GOLD"]
        elif world_type == "arena":
            w, h = 40, 120; grid = [[-1]*w for _ in range(h)]
            for x in range(w):
                grid[h-5][x] = BLOCK_IDS["GRASS"]; grid[5][x] = BLOCK_IDS["DIAMOND"]
            for y in range(h): grid[y][0] = BLOCK_IDS["BRICK"]; grid[y][w-1] = BLOCK_IDS["BRICK"]
        
        world_json = json.dumps({"c2tilemap": True, "width": w, "height": h, "data": rle_encode(grid)})
        self.world_data_cache[world_type] = world_json
        return world_json

    async def add_player(self, username):
        if self.game_state != "waiting": return
        if len(self.players) >= config["max_players"]: return
        
        await self.despawn_player_from_main_world(username)
        self.players.add(username)
        player_to_game[username] = self.game_id
        
        await self.teleport_player(username, self.generate_world("lobby"), 800, 800)
        await self.broadcast_to_game_players(f"TELLRAW|PLACERSERVER|{username} joined! ({len(self.players)}/{config['max_players']})")
        
        if len(self.players) >= config["min_players"] and not any(t.get_name() == "countdown" for t in self.tasks):
            self.start_countdown()

    def start_countdown(self):
        async def countdown_task():
            try:
                self.game_state = "countdown"
                for i in range(config["countdown_normal"], 0, -1):
                    if i % 10 == 0 or i <= 5: await self.broadcast_to_game_players(f"TELLRAW|PLACERSERVER|Game starting in {i}...")
                    await asyncio.sleep(1)
                
                if len(self.players) >= config["min_players"]: await self.start_game()
                else: self.game_state = "waiting"; await self.broadcast_to_game_players("TELLRAW|PLACERSERVER|Not enough players.")
            except asyncio.CancelledError:
                self.game_state = "waiting"; await self.broadcast_to_game_players("TELLRAW|PLACERSERVER|Countdown cancelled.")
        
        self.tasks.append(asyncio.create_task(countdown_task(), name="countdown"))

    async def start_game(self):
        self.game_state = "playing"
        self.in_game_players = self.players.copy()
        
        arena_json = self.generate_world("arena")
        for username in self.in_game_players:
            spawn_x, spawn_y = (40 * TILE_SIZE) / 2, (120 - 10) * TILE_SIZE
            await self.teleport_player(username, arena_json, spawn_x, spawn_y)
        
        self.tasks.append(asyncio.create_task(self.game_loop(), name="game_loop"))
        self.tasks.append(asyncio.create_task(self.light_cycle_loop(), name="light_cycle"))
        await self.broadcast_to_game_players("TELLRAW|PLACERSERVER|GAME STARTED! Reach the finish line!")

    async def game_loop(self):
        start_time = asyncio.get_event_loop().time()
        while self.game_state == "playing":
            try:
                if asyncio.get_event_loop().time() - start_time > config["game_duration_seconds"]:
                    self.end_game(winner=None); break
                
                for username in list(self.in_game_players):
                    current_pos = player_locations.get(username)
                    if not current_pos: continue
                    
                    if self.light_state == "red":
                        last_pos = self.player_last_positions.get(username)
                        if last_pos and (last_pos['x'] != current_pos['x'] or last_pos['y'] != current_pos['y']):
                            await self.eliminate_player(username, "moved during Red Light!")
                    
                    if current_pos['y'] < (6 * TILE_SIZE): # Crossed finish line
                        self.end_game(winner=username); break
                
                await asyncio.sleep(0.1)
            except asyncio.CancelledError: break
            except Exception as e: self.server_api.log(f"RLGL Error (GameLoop): {e}")

    async def light_cycle_loop(self):
        while self.game_state == "playing":
            try:
                # Green Light
                self.light_state = "green"
                flash_img = await generate_flash_image((0, 255, 0, 128))
                if flash_img: await self.broadcast_to_game_players(f"SHOW_IMAGE|PLACERSERVER|{flash_img}"); asyncio.create_task(self.hide_image_after(0.5))
                await generate_and_broadcast_light_image(self, "green")
                
                green_light_end_time = asyncio.get_event_loop().time() + random.uniform(config["min_green_light_seconds"], config["max_green_light_seconds"])
                while asyncio.get_event_loop().time() < green_light_end_time and self.game_state == "playing":
                    self.doll_facing_direction = random.choice([0, 1]); await self.update_doll_npc(); await asyncio.sleep(0.75)
                
                if self.game_state != "playing": break

                # Red Light
                self.light_state = "red"; self.doll_facing_direction = 0; self.player_last_positions = player_locations.copy()
                flash_img = await generate_flash_image((255, 0, 0, 128))
                if flash_img: await self.broadcast_to_game_players(f"SHOW_IMAGE|PLACERSERVER|{flash_img}"); asyncio.create_task(self.hide_image_after(0.5))
                await self.update_doll_npc()
                await generate_and_broadcast_light_image(self, "red")
                
                await asyncio.sleep(random.uniform(config["min_red_light_seconds"], config["max_red_light_seconds"]))
                await self.broadcast_to_game_players("HIDE_IMAGE|PLACERSERVER|")
            except asyncio.CancelledError: break
            except Exception as e: self.server_api.log(f"RLGL Error (LightLoop): {e}")

    async def eliminate_player(self, username, reason):
        if username not in self.in_game_players: return
        self.in_game_players.discard(username)
        self.eliminated_players.add(username)
        await self.broadcast_to_game_players(f"TELLRAW|PLACERSERVER|{username} was eliminated: {reason}")
        await self.teleport_player(username, self.generate_world("arena"), TILE_SIZE*2, TILE_SIZE*10, no_world_send=True)

    def end_game(self, winner):
        if self.game_state == "ended": return
        self.game_state = "ended"
        for task in self.tasks: task.cancel()
        self.tasks.clear()
        asyncio.create_task(self._end_game_task(winner))

    async def _end_game_task(self, winner):
        try:
            await self.broadcast_to_game_players("HIDE_IMAGE|PLACERSERVER|"); await self.despawn_doll_npc()
            
            if winner: update_player_stat(winner, "wins", 1); await generate_end_game_image(self, winner)
            else: await generate_end_game_image(self, None)

            await asyncio.sleep(8)
            
            lobby_pos = config.get("lobby_location"); main_world_json = "{}"
            try:
                with open("worlds/world.pw", 'r') as f: main_world_json = f.read()
            except Exception as e: self.server_api.log(f"RLGL_EndGame: Failed to load main world: {e}")

            for username in list(self.players):
                if username in player_to_game: del player_to_game[username]
                await self.teleport_player(username, main_world_json, lobby_pos['x'], lobby_pos['y'])
            
            if self.game_id in active_games: del active_games[self.game_id]
            if not active_games: self.server_api.clear_broadcast_override()
        except Exception as e: self.server_api.log(f"RLGL Error (_end_game_task): {e}")

    async def remove_player(self, username):
        self.players.discard(username); self.in_game_players.discard(username); self.eliminated_players.discard(username)
        if username in player_to_game: del player_to_game[username]
        
        await self.broadcast_to_game_players(f"TELLRAW|PLACERSERVER|{username} left.")
        await self.broadcast_to_game_players(f"{username}|-999|-999|Default|0|0|PLAYER_INFO") # Despawn for others in game

        if len(self.in_game_players) < 1 and self.game_state == "playing": self.end_game(winner=None)
        if len(self.players) < config["min_players"] and self.game_state == "countdown":
            for t in self.tasks:
                if t.get_name() == "countdown": t.cancel()

    # --- Helper Methods ---
    async def hide_image_after(self, delay):
        await asyncio.sleep(delay)
        await self.broadcast_to_game_players("HIDE_IMAGE|PLACERSERVER|")

    async def update_doll_npc(self):
        doll_name = f"RLGL DOLL-{self.game_id}"; doll_x, doll_y = (40*TILE_SIZE)/2, (5*TILE_SIZE)-80
        msg = f"{doll_name}|{int(doll_x)}|{int(doll_y)}|GameNPC|{self.doll_facing_direction}|{self.doll_npc_id}|PLAYER_INFO"
        await self.broadcast_to_game_players(msg)

    async def despawn_doll_npc(self):
        await self.broadcast_to_game_players(f"RLGL DOLL-{self.game_id}|-999|-999|Default|0|0|PLAYER_INFO")

    async def teleport_player(self, username, world_json, px, py, no_world_send=False):
        ws = self.server_api.get_websocket_from_username(username)
        if ws:
            if not no_world_send: await self.server_api.send_to_client(ws, f"WORLD_DATA|PLACERSERVER|{world_json}"); await asyncio.sleep(0.1)
            await self.server_api.send_to_client(ws, f"SET_POSITION|PLACERSERVER|{px}|{py}|{username}")
    
    async def broadcast_to_game_players(self, message):
        for username in list(self.players):
            ws = self.server_api.get_websocket_from_username(username)
            if ws: await self.server_api.send_to_client(ws, message)

    async def despawn_player_from_main_world(self, username):
        despawn_msg = f"{username}|-999|-999|Default|0|0|PLAYER_INFO"
        main_ws = [ws for ws in self.server_api.get_connected_clients() if self.server_api.get_username_from_websocket(ws) not in player_to_game]
        if main_ws: await asyncio.gather(*[ws.send(despawn_msg) for ws in main_ws], return_exceptions=True)

# --- Global Broadcast and Plugin Hooks ---
async def minigame_broadcast_override(server_api, message, exclude_websocket=None):
    try:
        parts = message.split('|'); sender_username = None
        if "PLAYER_INFO" in message: sender_username = parts[0]
        elif len(parts) > 2 and "PLACERCLIENT" in message: sender_username = parts[2]
        elif exclude_websocket: sender_username = server_api.get_username_from_websocket(exclude_websocket)

        sender_game_id = player_to_game.get(sender_username)
        if sender_game_id is not None:
            game = active_games.get(sender_game_id)
            if game:
                targets = [server_api.get_websocket_from_username(p) for p in game.players if server_api.get_websocket_from_username(p) != exclude_websocket]
                if targets: await asyncio.gather(*[ws.send(message) for ws in targets if ws], return_exceptions=True)
        else:
            main_ws = [ws for ws in server_api.get_connected_clients() if server_api.get_username_from_websocket(ws) not in player_to_game and ws != exclude_websocket]
            if main_ws: await asyncio.gather(*[ws.send(message) for ws in main_ws], return_exceptions=True)
    except Exception as e: server_api.log(f"RLGL Broadcast Override Error: {e}")

async def global_periodic_broadcast(server_api):
    global last_npc_name
    while True:
        try:
            total_players = sum(len(game.players) for game in active_games.values())
            npc_name = f"RLGL ({total_players} Playing)"
            main_ws = [ws for ws in server_api.get_connected_clients() if server_api.get_username_from_websocket(ws) not in player_to_game]
            
            if npc_name != last_npc_name and last_npc_name and main_ws:
                 await asyncio.gather(*[ws.send(f"{last_npc_name}|-999|-999|Default|0|0|PLAYER_INFO") for ws in main_ws], return_exceptions=True)
            
            if npc_location and main_ws:
                msg = f"{npc_name}|{int(npc_location['x'])}|{int(npc_location['y'])}|{npc_location.get('skin', 'GameNPC')}|999|100|PLAYER_INFO"
                last_npc_name = npc_name
                await asyncio.gather(*[ws.send(msg) for ws in main_ws], return_exceptions=True)
            await asyncio.sleep(1)
        except asyncio.CancelledError: break
        except Exception as e: server_api.log(f"RLGL Global Broadcast Error: {e}")

# --- Plugin API ---
def on_load(server_api):
    global global_broadcast_task
    server_api.log("RLGL Plugin: Loading..."); load_all()
    if global_broadcast_task: global_broadcast_task.cancel()
    global_broadcast_task = asyncio.create_task(global_periodic_broadcast(server_api))
    server_api.log("RLGL Plugin: Loaded!")

def on_unload(server_api):
    if global_broadcast_task: global_broadcast_task.cancel()
    for game in list(active_games.values()): game.end_game(winner=None)
    if active_games: server_api.clear_broadcast_override()
    server_api.log("RLGL Plugin: Unloaded.")

async def on_connect(websocket, server_api):
    if npc_location:
        total_players = sum(len(game.players) for game in active_games.values())
        msg = f"RLGL ({total_players} Playing)|{int(npc_location['x'])}|{int(npc_location['y'])}|{npc_location.get('skin', 'GameNPC')}|999|100|PLAYER_INFO"
        await server_api.send_to_client(websocket, msg)

async def on_message(websocket, message, parts, server_api):
    global next_game_id
    username = server_api.get_username_from_websocket(websocket)
    if not username: return False
    
    if len(parts) >= 7 and parts[6] == "PLAYER_INFO" and username:
        try: player_locations[username] = {"x": int(parts[1]), "y": int(parts[2])}
        except (ValueError, IndexError): pass
            
    if len(parts) >= 4 and parts[1] == "PLACERCLIENT":
        if parts[0] == "PLAYER_MESSAGE":
            command = parts[3].strip().lower()
            if command == "!rlgl_npc" and username in player_locations and username not in player_to_game:
                global npc_location
                npc_location = {**player_locations[username], "skin": "GameNPC"}
                with open(NPC_FILE, 'w') as f: json.dump(npc_location, f, indent=4)
                await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|RLGL Game NPC spawned.")
                return True

        elif parts[0] == "DAMAGE":
            target_name, damager = parts[2], parts[3]
            if target_name.startswith("RLGL") and damager not in player_to_game:
                # This is the stable joining logic from Zombies.py
                target_game = next((g for g in active_games.values() if g.game_state == "waiting" and len(g.players) < config["max_players"]), None)
                if not target_game:
                    if not active_games: server_api.set_broadcast_override(functools.partial(minigame_broadcast_override, server_api))
                    target_game = GameInstance(next_game_id, server_api)
                    active_games[next_game_id] = target_game; next_game_id += 1
                await target_game.add_player(damager)
                return True
    return False

async def on_disconnect(websocket, server_api):
    username = server_api.get_username_from_websocket(websocket)
    if username:
        if username in player_to_game:
            game_id = player_to_game[username]
            if game_id in active_games: await active_games[game_id].remove_player(username)
        if username in player_locations: del player_locations[username]

