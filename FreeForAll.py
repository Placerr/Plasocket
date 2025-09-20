import asyncio
import math
import random
import time
import base64
import importlib
import json
import os
import functools
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

# --- Attempt to import the ObjectRenderAPI (No longer used) ---
# try:
#     ObjectRenderAPI = importlib.import_module("ObjectRenderAPI")
# except ImportError:
#     ObjectRenderAPI = None

# --- Plugin Configuration ---
PLUGIN_FOLDER = "plugins/FreeForAllGame"
CONFIG_FILE = os.path.join(PLUGIN_FOLDER, "config.json")
NPC_FILE = os.path.join(PLUGIN_FOLDER, "npc_location.json")
FONT_PATH_REGULAR = os.path.join(PLUGIN_FOLDER, "font.ttf")
FONT_PATH_BOLD = os.path.join(PLUGIN_FOLDER, "arial_black.ttf")

# --- Default Configuration ---
DEFAULT_CONFIG = {
    "min_players": 2,
    "max_players": 8,
    "countdown_normal": 30,
    "countdown_full": 10,
    "lobby_location": {"x": 500, "y": 500},
    "win_kill_count": 10,
    "reload_time_seconds": 2.5
}

# --- Global State ---
config = {}
active_games = {}
player_to_game = {}
next_game_id = 1
# object_render_api = None # Gun model removed
player_locations = {}
npc_location = {}
global_broadcast_task = None
last_npc_name = ""
font_large = None
font_medium = None
font_small = None
game_creation_lock = asyncio.Lock() 

# --- Constants ---
PLAYER_SPRITE_HEIGHT = 190
PLAYER_SPRITE_WIDTH = 50
PLAYER_CENTER_Y_OFFSET = PLAYER_SPRITE_HEIGHT / 2
PROJECTILE_SPEED = 30 
PROJECTILE_LIFETIME_S = 1.5
MAX_HEALTH = 100
MAX_AMMO = 30
TILE_SIZE = 40

# --- M4 Weapon Model Definition (No longer used) ---
# m4_model = { ... }

# --- New HUD generation system modeled after Zombies.py ---
def load_font():
    global font_large, font_medium, font_small
    try:
        # FIX: Reduced font sizes by ~20% from the previous version
        font_large = ImageFont.truetype(FONT_PATH_BOLD, 80 * 2) 
        font_medium = ImageFont.truetype(FONT_PATH_REGULAR, 48 * 2)
        font_small = ImageFont.truetype(FONT_PATH_REGULAR, 36 * 2)
        print("FreeForAll: Custom fonts loaded successfully.")
    except IOError:
        print("FreeForAll: WARNING - Font files not found. Falling back to default font. Text will be small and pixelated.")
        font_large, font_medium, font_small = ImageFont.load_default(), ImageFont.load_default(), ImageFont.load_default()

async def generate_and_broadcast_hud(game_instance, username):
    # --- Using a copy to prevent race condition crashes on disconnect ---
    player = game_instance.players.get(username)
    if not player: return
    try:
        scale = 2 
        canvas_width, canvas_height = 854, 480
        img = Image.new('RGBA', (canvas_width * scale, canvas_height * scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Health Bar
        hp_bar_width, hp_bar_height = 300, 35
        hp_bar_x, hp_bar_y = 40, canvas_height - hp_bar_height - 20
        health_percentage = player.health / MAX_HEALTH
        draw.rounded_rectangle(
            (hp_bar_x * scale, hp_bar_y * scale, (hp_bar_x + hp_bar_width) * scale, (hp_bar_y + hp_bar_height) * scale),
            fill=(0, 0, 0, 150), radius=8 * scale
        )
        if health_percentage > 0:
            draw.rounded_rectangle(
                (hp_bar_x * scale, hp_bar_y * scale, (hp_bar_x + (hp_bar_width * health_percentage)) * scale, (hp_bar_y + hp_bar_height) * scale),
                fill=(70, 220, 90, 200), radius=8 * scale
            )
        hp_text = f"{player.health} / {MAX_HEALTH}"
        hp_text_bbox = draw.textbbox((0, 0), hp_text, font=font_small)
        hp_text_width = hp_text_bbox[2] - hp_text_bbox[0]
        hp_text_x = (hp_bar_x * scale) + ((hp_bar_width * scale) - hp_text_width) / 2
        draw.text(
            (hp_text_x, (hp_bar_y + 2) * scale),
            hp_text, font=font_small, fill=(255, 255, 255)
        )

        # Ammo Display
        ammo_bg_width, ammo_bg_height = 300, 100
        ammo_bg_x, ammo_bg_y = canvas_width - ammo_bg_width - 20, canvas_height - ammo_bg_height - 20
        draw.rounded_rectangle(
            (ammo_bg_x * scale, ammo_bg_y * scale, (ammo_bg_x + ammo_bg_width) * scale, (ammo_bg_y + ammo_bg_height) * scale),
            fill=(0, 0, 0, 150), radius=8 * scale
        )
        ammo_text = f"{player.ammo} / {MAX_AMMO}"
        if player.is_reloading: ammo_text = "RELOADING..."
        ammo_bbox = draw.textbbox((0, 0), ammo_text, font=font_large)
        ammo_text_width = ammo_bbox[2] - ammo_bbox[0]
        ammo_text_x = (ammo_bg_x * scale) + ((ammo_bg_width * scale) - ammo_text_width) / 2
        draw.text(
            (ammo_text_x, (ammo_bg_y + 15) * scale),
            ammo_text, font=font_large, fill=(255, 255, 255)
        )

        # Leaderboard
        # --- Using list() to prevent race condition crashes on disconnect ---
        ingame_players_list = list(p for p in game_instance.players.values() if p.username in game_instance.in_game_players)
        sorted_players = sorted(ingame_players_list, key=lambda p: (p.kills, -p.deaths), reverse=True)
        
        num_players_to_show = min(len(sorted_players), 5)
        if num_players_to_show > 0:
            lb_line_height = 38
            lb_width, lb_height = 350, 50 + (num_players_to_show * lb_line_height)
            lb_x, lb_y = canvas_width - lb_width - 20, 20
            draw.rounded_rectangle(
                (lb_x * scale, lb_y * scale, (lb_x + lb_width) * scale, (lb_y + lb_height) * scale),
                fill=(0, 0, 0, 150), radius=8 * scale
            )
            draw.text(((lb_x + 15) * scale, (lb_y + 8) * scale), "SCOREBOARD", font=font_small, fill=(200, 200, 200))
            for i, p in enumerate(sorted_players[:num_players_to_show]):
                player_text = f"#{i+1} {p.username[:12]:<12} {p.kills:>2}K / {p.deaths:>2}D"
                text_color = (255, 215, 0) if p.username == username else (255, 255, 255)
                draw.text(((lb_x + 15) * scale, (lb_y + 45 + (i * lb_line_height)) * scale), player_text, font=font_small, fill=text_color)

        img = img.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)
        buffer = BytesIO(); img.save(buffer, format="PNG")
        data_url = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('utf-8')}"
        ws = game_instance.server_api.get_websocket_from_username(username)
        if ws: await game_instance.server_api.send_to_client(ws, f"SHOW_IMAGE|PLACERSERVER|{data_url}")
    except Exception as e:
        game_instance.server_api.log(f"[FreeForAll HUD] Error: {e}")

# --- Utility Functions ---
def load_config():
    global config
    if not os.path.exists(PLUGIN_FOLDER): os.makedirs(PLUGIN_FOLDER)
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f: config = json.load(f)
    else: config = DEFAULT_CONFIG.copy()
    for key, value in DEFAULT_CONFIG.items():
        if key not in config: config[key] = value
    save_config()

def save_config():
    with open(CONFIG_FILE, 'w') as f: json.dump(config, f, indent=4)

def load_npc_location():
    global npc_location
    if os.path.exists(NPC_FILE):
        with open(NPC_FILE, 'r') as f: npc_location = json.load(f)

def save_npc_location():
    with open(NPC_FILE, 'w') as f: json.dump(npc_location, f, indent=4)

def rle_encode(grid, width, height):
    parts = []; flat_list = [item for sublist in grid for item in sublist]
    if not flat_list: return ""
    current_id, count = flat_list[0], 1
    for block_id in flat_list[1:]:
        if block_id == current_id: count += 1
        else:
            parts.append(f"{count}x{current_id}" if count > 1 else str(current_id))
            current_id, count = block_id, 1
    parts.append(f"{count}x{current_id}" if count > 1 else str(current_id))
    return ",".join(parts)

class Player:
    def __init__(self, username):
        self.username = username
        self.health = MAX_HEALTH
        self.ammo = MAX_AMMO
        self.kills = 0
        self.deaths = 0
        self.last_shot_time = 0
        self.is_reloading = False
        self.reload_task = None

    def take_damage(self, amount):
        self.health -= amount
        if self.health <= 0:
            self.health = 0
            return True
        return False

    def respawn(self):
        self.health = MAX_HEALTH
        self.ammo = MAX_AMMO
        self.is_reloading = False
        if self.reload_task: self.reload_task.cancel()

class GameInstance:
    def __init__(self, game_id, server_api):
        self.game_id = game_id
        self.server_api = server_api
        self.state = "waiting"
        self.players = {} # Using dict to store Player objects
        self.lobby_players = set()
        self.in_game_players = set()
        self.projectiles = []
        self.next_projectile_id = 0
        self.next_death_object_id = 0
        self.next_hit_object_id = 0
        self.game_loop_task = None
        self.countdown_task = None
        self.world_data_cache = {}
        
        spawn_point_tiles = [
            (25, 59), (95, 59), (60, 44), (20, 74), (100, 74), (60, 74)
        ]
        self.spawn_points = [(tx * TILE_SIZE, ty * TILE_SIZE) for tx, ty in spawn_point_tiles]

    def generate_world(self, is_game_world=False):
        world_key = "game" if is_game_world else "lobby"
        if world_key in self.world_data_cache: return self.world_data_cache[world_key]
        
        if is_game_world:
            width, height = 120, 80
            world_data = [[-1 for _ in range(width)] for _ in range(height)]
            ground_level = height - 5
            for x in range(width):
                for y in range(ground_level, height): world_data[y][x] = 2
            for y in range(20, ground_level):
                world_data[y][0] = 2; world_data[y][1] = 2
                world_data[y][width - 1] = 2; world_data[y][width - 2] = 2
            for x in range(10, 40): world_data[60][x] = 18
            for x in range(width - 40, width - 10): world_data[60][x] = 18
            for x in range(50, 70): world_data[45][x] = 18
        else:
            width, height = 50, 40
            world_data = [[-1 for _ in range(width)] for _ in range(height)]
            for x in range(width): world_data[height - 10][x], world_data[10][x] = 18, 18
            for y in range(10, height - 9): world_data[y][0], world_data[y][width - 1] = 18, 18
        world_json = json.dumps({"c2tilemap": True, "width": width, "height": height, "data": rle_encode(world_data, width, height)})
        self.world_data_cache[world_key] = world_json
        return world_json

    async def add_player(self, username):
        if self.state not in ["waiting", "countdown"]:
            ws = self.server_api.get_websocket_from_username(username)
            if ws: await self.server_api.send_to_client(ws, "TELLRAW|PLACERSERVER|This game has already started.")
            return
        if len(self.players) >= config["max_players"]:
            ws = self.server_api.get_websocket_from_username(username)
            if ws: await self.server_api.send_to_client(ws, "TELLRAW|PLACERSERVER|This game is full.")
            return

        despawn_msg = f"{username}|-999|-999|Default|0|0|PLAYER_INFO"
        main_world_websockets = [ws for ws in self.server_api.get_connected_clients() if self.server_api.get_username_from_websocket(ws) not in player_to_game]
        if main_world_websockets: await asyncio.gather(*[ws.send(despawn_msg) for ws in main_world_websockets], return_exceptions=True)

        self.players[username] = Player(username)
        self.lobby_players.add(username)
        player_to_game[username] = self.game_id
        
        lobby_world_json = self.generate_world(is_game_world=False)
        lobby_spawn_x = 25 * TILE_SIZE; lobby_spawn_y = 20 * TILE_SIZE
        await self.teleport_player(username, lobby_world_json, lobby_spawn_x, lobby_spawn_y)
        
        join_msg = f"TELLRAW|PLACERSERVER|{username} joined! ({len(self.players)}/{config['max_players']})"
        await self.broadcast_to_game_players(join_msg)
        
        if len(self.players) >= config["min_players"] and self.state == "waiting": self.start_countdown()
        elif len(self.players) == config["max_players"]: self.start_countdown()

    def start_countdown(self):
        if self.countdown_task and not self.countdown_task.done(): self.countdown_task.cancel()
        self.countdown_task = asyncio.create_task(self._countdown())

    async def _countdown(self):
        try:
            self.state = "countdown"
            wait_time = config["countdown_full"] if len(self.players) == config["max_players"] else config["countdown_normal"]
            for i in range(wait_time, 0, -1):
                if i <= 5 or i % 5 == 0: await self.broadcast_to_game_players(f"TELLRAW|PLACERSERVER|Game starting in {i}...")
                await asyncio.sleep(1)
            
            if len(self.players) >= config["min_players"]: await self.start_game()
            else:
                self.state = "waiting"
                await self.broadcast_to_game_players("TELLRAW|PLACERSERVER|Not enough players. Countdown cancelled.")
        except asyncio.CancelledError:
            self.state = "waiting"
            await self.broadcast_to_game_players("TELLRAW|PLACERSERVER|Countdown cancelled.")

    async def start_game(self):
        self.state = "playing"
        self.in_game_players = self.lobby_players.copy()
        self.lobby_players.clear()
        game_world_json = self.generate_world(is_game_world=True)
        spawn_locations = random.sample(self.spawn_points, k=min(len(self.in_game_players), len(self.spawn_points)))
        
        tasks = []
        for i, username in enumerate(self.in_game_players):
            ws = self.server_api.get_websocket_from_username(username)
            if ws: await self.server_api.send_to_client(ws, "TOUCH_SENSOR|PLACERSERVER|1")
            spawn_x, spawn_y = spawn_locations[i % len(spawn_locations)]
            tasks.append(self.teleport_player(username, game_world_json, spawn_x, spawn_y))
        await asyncio.gather(*tasks)
        
        await self.broadcast_to_game_players("DISABLE_BREAKING|PLACERSERVER|1")
        await self.broadcast_to_game_players(f"KILL_LOG|PLACERSERVER|")
        await self.broadcast_to_game_players(f"TELLRAW|PLACERSERVER|Match Started! First to {config['win_kill_count']} kills wins!")
        for username in self.in_game_players: await generate_and_broadcast_hud(self, username)
        self.game_loop_task = asyncio.create_task(self.game_loop())

    async def end_game(self, was_cancelled_by_disconnect=False):
        if self.state == "ended": return
        self.state = "ended"
        
        for task in [self.game_loop_task, self.countdown_task]:
            if task and not task.done(): task.cancel()
        for player in self.players.values():
            if player.reload_task and not player.reload_task.done(): player.reload_task.cancel()
        
        await self.broadcast_to_game_players("KILL_LOG|PLACERSERVER|")
        
        if was_cancelled_by_disconnect:
            await self.broadcast_to_game_players(f"TELLRAW|PLACERSERVER|Match ended due to players leaving.")
        else:
            winner = max(list(self.players.values()), key=lambda p: p.kills, default=None) if self.players else None
            win_msg = f"Match Over! {winner.username} wins with {winner.kills} kills!" if winner else "Match Over!"
            await self.broadcast_to_game_players(f"TELLRAW|PLACERSERVER|{win_msg}")

        await asyncio.sleep(5)
        
        lobby_pos = config.get("lobby_location", {"x": 500, "y": 500})
        
        main_world_json = "{}"
        try:
            loop = asyncio.get_event_loop()
            def read_world_sync():
                with open("worlds/world.pw", 'r') as f: return f.read()
            main_world_json = await loop.run_in_executor(None, read_world_sync)
        except Exception: 
            self.server_api.log("[FreeForAll] WARNING: worlds/world.pw not found. Players will be sent to a void world.")
            
        players_to_teleport = list(self.players.keys())
        tasks = [self.clean_up_player_on_exit(username, teleport_out=True, world_json=main_world_json, pos=lobby_pos) for username in players_to_teleport]
        if tasks: await asyncio.gather(*tasks)
        
        self.players.clear(); self.in_game_players.clear(); self.lobby_players.clear()
        if self.game_id in active_games: del active_games[self.game_id]
        
        if not active_games:
            self.server_api.clear_broadcast_override()
            self.server_api.log("FreeForAll: Last game ended, broadcast override released.")

    async def game_loop(self):
        while self.state == "playing":
            try:
                projectiles_to_remove = []
                for proj in self.projectiles:
                    proj['x'] += proj['vx']; proj['y'] += proj['vy']; proj['life'] -= 0.05
                    if proj['life'] <= 0: projectiles_to_remove.append(proj)
                    
                    await self.broadcast_to_game_players(f"OBJECT_MODIFY|PLACERSERVER|9|{int(proj['x'])}|{int(proj['y'])}|10|10|{proj['id']}")
                    
                    for username, player in list(self.players.items()):
                        if username not in self.in_game_players or username == proj['owner']: continue
                        player_pos = player_locations.get(username)
                        
                        if player_pos:
                            player_center_y = player_pos['y'] - PLAYER_CENTER_Y_OFFSET
                            hit_x = abs(proj['x'] - player_pos['x']) < (PLAYER_SPRITE_WIDTH / 2)
                            hit_y = abs(proj['y'] - player_center_y) < PLAYER_CENTER_Y_OFFSET
                            if hit_x and hit_y:
                                await self.handle_player_hit(proj['owner'], username)
                                projectiles_to_remove.append(proj)
                                break
                
                # BUG FIX: Replaced 'set()' with a manual de-duplication to fix "unhashable type: dict" error.
                unique_projectiles_to_remove = []
                for proj in projectiles_to_remove:
                    if proj not in unique_projectiles_to_remove:
                        unique_projectiles_to_remove.append(proj)

                for proj in unique_projectiles_to_remove:
                    if proj in self.projectiles:
                        self.projectiles.remove(proj)
                        await self.broadcast_to_game_players(f"OBJECT_DESTROY|PLACERSERVER|{proj['id']}")
                await asyncio.sleep(1/20)
            except asyncio.CancelledError: break
            except Exception as e: 
                self.server_api.log(f"[FreeForAll {self.game_id}] Loop Error: {type(e).__name__} - {e}")


    async def play_death_effect(self, username):
        try:
            player_pos = player_locations.get(username)
            if not player_pos: return
            obj_id = f"death_{self.game_id}_{self.next_death_object_id}"; self.next_death_object_id += 1
            start_x, start_y = int(player_pos['x']), int(player_pos['y'])
            await self.broadcast_to_game_players(f"OBJECT|PLACERSERVER|0|{start_x}|{start_y}|{PLAYER_SPRITE_WIDTH}|{PLAYER_SPRITE_HEIGHT}|{obj_id}")
            for i in range(10):
                scale = 1.0 - (i / 10.0)
                new_width, new_height = int(PLAYER_SPRITE_WIDTH * scale), int(PLAYER_SPRITE_HEIGHT * scale)
                if new_width < 1 or new_height < 1: break
                await self.broadcast_to_game_players(f"OBJECT_MODIFY|PLACERSERVER|0|{start_x}|{start_y}|{new_width}|{new_height}|{obj_id}")
                await asyncio.sleep(0.03)
            await self.broadcast_to_game_players(f"OBJECT_DESTROY|PLACERSERVER|{obj_id}")
        except Exception as e:
            self.server_api.log(f"[FreeForAll] Death effect error for {username}: {e}")

    async def play_hit_effect(self, username):
        try:
            player_pos = player_locations.get(username)
            if not player_pos: return
            obj_id = f"hit_{self.game_id}_{self.next_hit_object_id}"; self.next_hit_object_id += 1
            start_x = int(player_pos['x']) + random.randint(-15, 15)
            start_y = int(player_pos['y'] - PLAYER_CENTER_Y_OFFSET) + random.randint(-30, 30)
            await self.broadcast_to_game_players(f"OBJECT|PLACERSERVER|2|{start_x}|{start_y}|15|15|{obj_id}")
            await asyncio.sleep(0.3)
            await self.broadcast_to_game_players(f"OBJECT_DESTROY|PLACERSERVER|{obj_id}")
        except Exception as e:
            self.server_api.log(f"[FreeForAll] Hit effect error for {username}: {e}")

    async def handle_player_hit(self, attacker_name, victim_name):
        victim = self.players.get(victim_name); attacker = self.players.get(attacker_name)
        if not victim or not attacker or self.state != "playing": return
        asyncio.create_task(self.play_hit_effect(victim_name))
        is_dead = victim.take_damage(34)
        if is_dead:
            attacker.kills += 1; victim.deaths += 1
            asyncio.create_task(self.play_death_effect(victim_name))
            await self.broadcast_to_game_players(f"KILL_LOG|PLACERSERVER|{attacker_name}|{victim_name}")
            for p_name in self.in_game_players: await generate_and_broadcast_hud(self, p_name)
            await self.respawn_player(victim_name)
            if attacker.kills >= config['win_kill_count']: await self.end_game()
        else: await generate_and_broadcast_hud(self, victim_name)

    async def respawn_player(self, username, is_initial_spawn=False):
        player = self.players.get(username)
        if not player: return
        if not is_initial_spawn: player.respawn()
        other_player_locs = [(loc['x'], loc['y']) for name, loc in player_locations.items() if name in self.in_game_players and name != username and loc]
        best_spawn = random.choice(self.spawn_points)
        if other_player_locs:
            max_dist = -1
            for sx, sy in self.spawn_points:
                min_dist_to_player = min([math.sqrt((sx - ox)**2 + (sy - oy)**2) for ox, oy in other_player_locs])
                if min_dist_to_player > max_dist: max_dist = min_dist_to_player; best_spawn = (sx, sy)
        spawn_x, spawn_y = best_spawn
        await self.teleport_player(username, None, spawn_x, spawn_y)
        await generate_and_broadcast_hud(self, username)

    async def player_shoot(self, username, touch_x, touch_y):
        player = self.players.get(username); player_pos = player_locations.get(username)
        if not player or not player_pos or player.health <= 0 or player.is_reloading: return
        if player.ammo <= 0: await self.player_reload(username); return
        current_time = time.time()
        if current_time - player.last_shot_time < 0.2: return
        player.last_shot_time = current_time; player.ammo -= 1

        start_x, start_y = player_pos['x'], player_pos['y']
        
        angle = math.atan2(touch_y - start_y, touch_x - start_x)
        vx, vy = math.cos(angle) * PROJECTILE_SPEED, math.sin(angle) * PROJECTILE_SPEED
        proj_id = f"proj_{self.game_id}_{self.next_projectile_id}"; self.next_projectile_id += 1
        self.projectiles.append({'id': proj_id, 'owner': username, 'x': start_x, 'y': start_y, 'vx': vx, 'vy': vy, 'life': PROJECTILE_LIFETIME_S})
        await self.broadcast_to_game_players(f"OBJECT|PLACERSERVER|9|{int(start_x)}|{int(start_y)}|10|10|{proj_id}")
        await generate_and_broadcast_hud(self, username)
    
    async def player_reload(self, username):
        player = self.players.get(username)
        if not player or player.is_reloading: return
        async def _reload():
            try:
                player.is_reloading = True; await generate_and_broadcast_hud(self, username)
                await asyncio.sleep(config['reload_time_seconds'])
                player.ammo = MAX_AMMO; player.is_reloading = False
                await generate_and_broadcast_hud(self, username)
            except asyncio.CancelledError: player.is_reloading = False
        player.reload_task = asyncio.create_task(_reload())

    async def clean_up_player_on_exit(self, username, teleport_out=False, world_json=None, pos=None):
        if username in player_to_game: del player_to_game[username]
        ws = self.server_api.get_websocket_from_username(username)
        if ws:
            await self.server_api.send_to_client(ws, "TOUCH_SENSOR|PLACERSERVER|0")
            await self.server_api.send_to_client(ws, "DISABLE_BREAKING|PLACERSERVER|0")
            await self.clear_hud(username)
            if teleport_out and world_json and pos:
                await self.teleport_player(username, world_json, pos['x'], pos['y'])

    async def remove_player(self, username):
        self.players.pop(username, None)
        self.lobby_players.discard(username)
        self.in_game_players.discard(username)
        if username in player_to_game: del player_to_game[username]

        despawn_msg = f"{username}|-999|-999|Default|0|0|PLAYER_INFO"
        await self.broadcast_to_game_players(despawn_msg)

        leave_msg = f"TELLRAW|PLACERSERVER|{username} left the game. ({len(self.players)}/{config['max_players']})"
        await self.broadcast_to_game_players(leave_msg)

        if self.state == "countdown" and len(self.players) < config["min_players"]:
            if self.countdown_task: self.countdown_task.cancel()
        if self.state == "playing" and len(self.in_game_players) < config["min_players"]:
            self.server_api.log(f"[FreeForAll {self.game_id}] Player count below minimum. Ending game.")
            await self.end_game(was_cancelled_by_disconnect=True)
        if not self.players and self.state != "ended":
            self.server_api.log(f"[FreeForAll {self.game_id}] Last player left. Ending game.")
            await self.end_game(was_cancelled_by_disconnect=True)

    async def clear_hud(self, username):
        ws = self.server_api.get_websocket_from_username(username)
        if ws: await self.server_api.send_to_client(ws, "HIDE_IMAGE|PLACERSERVER|")

    async def teleport_player(self, username, world_json, x, y):
        ws = self.server_api.get_websocket_from_username(username)
        if ws:
            if world_json:
                await self.server_api.send_to_client(ws, f"WORLD_DATA|PLACERSERVER|{world_json}")
                await asyncio.sleep(1.0) 
            await self.server_api.send_to_client(ws, f"SET_POSITION|PLACERSERVER|{x}|{y}|{username}")
    
    async def broadcast_to_game_players(self, message):
        tasks = [self.server_api.send_to_client(self.server_api.get_websocket_from_username(u), message) for u in self.players if self.server_api.get_websocket_from_username(u)]
        if tasks: await asyncio.gather(*tasks, return_exceptions=True)

async def minigame_broadcast_override(server_api, message, exclude_websocket=None):
    try:
        sender_username = None; parts = message.split('|'); msg_type = parts[0]
        if msg_type == "PLAYER_INFO" or msg_type.endswith("PLAYER_INFO"): sender_username = parts[0]
        elif msg_type == "PLAYER_MESSAGE": sender_username = parts[2]
        elif exclude_websocket: sender_username = server_api.get_username_from_websocket(exclude_websocket)
        
        sender_game_id = player_to_game.get(sender_username)
        if sender_game_id is not None:
            game = active_games.get(sender_game_id)
            if game:
                targets = [server_api.get_websocket_from_username(p) for p in game.players if server_api.get_websocket_from_username(p) != exclude_websocket]
                if targets: await asyncio.gather(*[ws.send(message) for ws in targets if ws], return_exceptions=True)
        else:
            main_world_sockets = [ws for ws in server_api.get_connected_clients() if server_api.get_username_from_websocket(ws) not in player_to_game and ws != exclude_websocket]
            if main_world_sockets: await asyncio.gather(*[ws.send(message) for ws in main_world_sockets], return_exceptions=True)
    except Exception as e: server_api.log(f"FreeForAll broadcast override error: {e}")

async def global_periodic_broadcast(server_api):
    global last_npc_name
    while True:
        try:
            total_players = sum(len(game.players) for game in active_games.values())
            npc_name = f"Shooter ({total_players} Playing)"
            main_world_sockets = [ws for ws in server_api.get_connected_clients() if server_api.get_username_from_websocket(ws) and server_api.get_username_from_websocket(ws) not in player_to_game]
            if npc_name != last_npc_name and last_npc_name:
                 despawn_msg = f"{last_npc_name}|-999|-999|Default|0|0|PLAYER_INFO"
                 if main_world_sockets: await asyncio.gather(*[ws.send(despawn_msg) for ws in main_world_sockets], return_exceptions=True)
            if npc_location:
                msg = f"{npc_name}|{int(npc_location['x'])}|{int(npc_location['y'])}|GameNPC|997|100|PLAYER_INFO"
                last_npc_name = npc_name
                if main_world_sockets: await asyncio.gather(*[ws.send(msg) for ws in main_world_sockets], return_exceptions=True)
            await asyncio.sleep(1)
        except asyncio.CancelledError: break
        except Exception as e: server_api.log(f"FreeForAll global broadcast error: {e}")

def on_load(server_api):
    global global_broadcast_task
    server_api.log("FreeForAll Plugin: Loading...")
    load_config(); load_npc_location(); load_font()

    if global_broadcast_task: global_broadcast_task.cancel()
    global_broadcast_task = asyncio.create_task(global_periodic_broadcast(server_api))
    server_api.log("FreeForAll Plugin: Loaded!")

async def on_connect(websocket, server_api):
    username = server_api.get_username_from_websocket(websocket)
    if not username: return
    if username in player_to_game:
        server_api.log(f"FreeForAll: Found and removed ghost session for {username} on connect.")
        old_game_id = player_to_game.get(username)
        if old_game_id is not None and old_game_id in active_games:
            await active_games[old_game_id].remove_player(username)

async def on_disconnect(websocket, server_api):
    username = server_api.get_username_from_websocket(websocket)
    if username and username in player_to_game:
        game_id = player_to_game[username]
        game = active_games.get(game_id)
        if game:
            await game.remove_player(username)
    if username and username in player_locations:
        del player_locations[username]

async def on_message(websocket, message_string, message_parts, server_api):
    global next_game_id
    username = server_api.get_username_from_websocket(websocket)
    if not username: return False
    msg_type = message_parts[0]

    if len(message_parts) >= 3 and message_parts[2] == "TouchSensor":
        game_id = player_to_game.get(username)
        if game_id is not None and game_id in active_games and active_games[game_id].state == "playing":
            try:
                coords = message_parts[1].split(',')
                touch_x = float(coords[0]); touch_y = float(coords[1])
                await active_games[game_id].player_shoot(username, touch_x, touch_y)
                return True
            except (ValueError, IndexError): pass
    
    if len(message_parts) >= 7 and message_parts[6] == "PLAYER_INFO":
        try:
            px, py = int(message_parts[1]), int(message_parts[2])

            game_id = player_to_game.get(username)
            if game_id is not None and username in active_games[game_id].in_game_players:
                max_x = 120 * TILE_SIZE + 500
                max_y = 80 * TILE_SIZE + 500
                if not (-500 < px < max_x and -500 < py < max_y):
                    return False 

            player_locations[message_parts[0]] = {'x': px, 'y': py, 'direction': int(message_parts[4])}
        except (ValueError, IndexError): pass

    if msg_type == "PLAYER_MESSAGE":
        command_user, command = message_parts[2], message_parts[3].strip()
        if command_user == username and username not in player_to_game:
            if command == "!shooter_npc":
                if last_npc_name:
                    await server_api.broadcast(f"{last_npc_name}|-999|-999|Default|0|0|PLAYER_INFO")
                if username in player_locations:
                    npc_location.update({"x": player_locations[username]["x"], "y": player_locations[username]["y"]})
                    save_npc_location()
                    await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Shooter Game NPC spawned.")
                else:
                    await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Your location is not yet known.")
                return True

    if msg_type == "DAMAGE":
        target_name, damager_name = message_parts[2], message_parts[3]
        if damager_name == username and target_name.startswith("Shooter ("):
            if username in player_to_game: return True
            
            async with game_creation_lock:
                target_game = next((g for g in active_games.values() if g.state in ["waiting", "countdown"] and len(g.players) < config["max_players"]), None)
                if not target_game:
                    if not active_games:
                        override_func = functools.partial(minigame_broadcast_override, server_api)
                        server_api.set_broadcast_override(override_func)
                        server_api.log("FreeForAll: First game created, broadcast override is active.")
                    target_game = GameInstance(next_game_id, server_api)
                    active_games[next_game_id] = target_game; next_game_id += 1
            
            await target_game.add_player(username)
            return True
    return False

def on_unload(server_api):
    if global_broadcast_task: global_broadcast_task.cancel()
    for game in list(active_games.values()): asyncio.create_task(game.end_game())
    if active_games: server_api.clear_broadcast_override()
    server_api.log("FreeForAll Plugin: Unloaded.")

