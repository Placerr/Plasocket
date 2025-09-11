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
PLUGIN_FOLDER = "plugins/ZombiesGame"
CONFIG_FILE = os.path.join(PLUGIN_FOLDER, "config.json")
NPC_FILE = os.path.join(PLUGIN_FOLDER, "npc_location.json")
SCOREBOARD_NPC_FILE = os.path.join(PLUGIN_FOLDER, "scoreboard_npc_location.json")
STATS_FILE = os.path.join(PLUGIN_FOLDER, "player_stats.json")
FONT_FILE = os.path.join(PLUGIN_FOLDER, "font.ttf") 
END_GAME_FONT_FILE = os.path.join(PLUGIN_FOLDER, "arial_black.ttf")

# --- Constants ---
TILE_SIZE = 40
SKIN_HEIGHT = 190

# --- Default Configuration ---
DEFAULT_CONFIG = {
    "min_players": 2, "max_players": 8, "countdown_normal": 40, "countdown_full": 10,
    "zombies_per_round_base": 5, "zombies_increase_per_round": 1, "zombie_hp_base": 20,
    "zombie_hp_increase_per_round": 5, "master_zombie_hp_multiplier": 3, "zombie_speed": 4,
    "zombie_gravity": 8, "max_rounds": 5, "core_hp": 100,
    "lobby_location": {"x": 461, "y": 1104}
}

# --- Global State ---
config = {}
active_games = {}
player_to_game = {}
next_game_id = 0
player_locations = {}
npc_location = {}
scoreboard_npc_location = {}
player_stats = {}
global_broadcast_task = None
last_npc_name = ""
last_scoreboard_npc_name = ""
font = None
font_scaled = None
end_game_font = None
scoreboard_font_title = None
scoreboard_font_text = None


# --- Image Generation ---
async def generate_and_broadcast_hud(game_instance):
    """Generates a high-quality HUD image with game stats and broadcasts it to players."""
    try:
        scale = 2 
        canvas_width, canvas_height = 854, 480
        hud_width, hud_height = 500, 60
        bar_height = 20
        padding = 10
        radius = 10
        hud_x = (canvas_width - hud_width) // 2
        hud_y = 20
        zombies_left = sum(1 for z in game_instance.active_zombies.values() if not z.get("is_minion"))
        total_zombies = game_instance.total_zombies_in_round
        
        if total_zombies > 0:
            if len(game_instance.active_zombies) >= total_zombies:
                 progress = 0.0
            else:
                zombies_defeated = total_zombies - zombies_left
                progress = zombies_defeated / total_zombies
        else:
            progress = 0.0

        img = Image.new('RGBA', (canvas_width * scale, canvas_height * scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            (hud_x * scale, hud_y * scale, (hud_x + hud_width) * scale, (hud_y + hud_height) * scale), 
            fill=(20, 20, 20, 180), radius=radius * scale
        )
        bar_bg_y = hud_y + hud_height - bar_height - padding
        draw.rounded_rectangle(
            ((hud_x + padding) * scale, bar_bg_y * scale, (hud_x + hud_width - padding) * scale, (bar_bg_y + bar_height) * scale), 
            fill=(10, 10, 10, 255), radius=5 * scale
        )
        progress_bar_width = (hud_width - 2 * padding) * progress
        if progress_bar_width > 0:
            draw.rounded_rectangle(
                ((hud_x + padding) * scale, bar_bg_y * scale, (hud_x + padding + progress_bar_width) * scale, (bar_bg_y + bar_height) * scale), 
                fill=(70, 180, 90, 255), radius=5 * scale
            )
        round_text = f"Round {game_instance.current_round} / {config['max_rounds']}"
        zombies_text = f"Zombies Left: {zombies_left}"
        round_text_pos = ((hud_x + padding) * scale, (hud_y + 8) * scale)
        
        zombies_text_bbox = draw.textbbox((0,0), zombies_text, font=font_scaled)
        zombies_text_width = zombies_text_bbox[2] - zombies_text_bbox[0]
        
        zombies_text_pos = ((hud_x + hud_width - padding) * scale - zombies_text_width, (hud_y + 8) * scale)
        draw.text((round_text_pos[0] + 2, round_text_pos[1] - 2), round_text, font=font_scaled, fill=(0,0,0,150))
        draw.text(round_text_pos, round_text, font=font_scaled, fill=(255, 255, 255, 255))
        draw.text((zombies_text_pos[0] + 2, zombies_text_pos[1] - 2), zombies_text, font=font_scaled, fill=(0,0,0,150))
        draw.text(zombies_text_pos, zombies_text, font=font_scaled, fill=(255, 255, 255, 255))
        img = img.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        base64_data = base64.b64encode(buffer.read()).decode('utf-8')
        full_data_url = f"data:image/png;base64,{base64_data}"
        message = f"SHOW_IMAGE|PLACERSERVER|{full_data_url}"
        await game_instance.broadcast_to_game_players(message)
    except Exception as e:
        game_instance.server_api.log(f"ZombiesHUD: Error generating HUD: {e}")
        traceback.print_exc()

async def generate_and_broadcast_timer_image(game_instance, number):
    """Generates a lightweight image of a number for the countdown."""
    try:
        canvas_width, canvas_height = 854, 480
        img = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        text = str(number)
        
        text_bbox = draw.textbbox((0, 0), text, font=end_game_font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        position = ((canvas_width - text_width) / 2, (canvas_height - text_height) / 2 - 100)
        draw.text((position[0] + 5, position[1] + 5), text, font=end_game_font, fill=(0, 0, 0, 128))
        draw.text(position, text, font=end_game_font, fill=(255, 255, 255, 255))
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        base64_data = base64.b64encode(buffer.read()).decode('utf-8')
        full_data_url = f"data:image/png;base64,{base64_data}"
        message = f"SHOW_IMAGE|PLACERSERVER|{full_data_url}"
        await game_instance.broadcast_to_game_players(message)
    except Exception as e:
        game_instance.server_api.log(f"ZombiesTimer: Error generating timer image: {e}")
        traceback.print_exc()

async def generate_end_game_image(game_instance, result_text, color):
    """Generates a Victory or Defeat image."""
    try:
        canvas_width, canvas_height = 854, 480
        img = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        text_bbox = draw.textbbox((0, 0), result_text, font=end_game_font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        position = ((canvas_width - text_width) / 2, (canvas_height - text_height) / 2)
        draw.text((position[0] + 5, position[1] + 5), result_text, font=end_game_font, fill=(0, 0, 0, 128))
        draw.text(position, result_text, font=end_game_font, fill=color)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        base64_data = base64.b64encode(buffer.read()).decode('utf-8')
        full_data_url = f"data:image/png;base64,{base64_data}"
        message = f"SHOW_IMAGE|PLACERSERVER|{full_data_url}"
        await game_instance.broadcast_to_game_players(message)
    except Exception as e:
        game_instance.server_api.log(f"ZombiesEndScreen: Error generating image: {e}")
        traceback.print_exc()

async def generate_scoreboard_image():
    """Generates a leaderboard image of the top 5 players, floating in a larger canvas."""
    try:
        # Get and sort player data by wins, then kills, then games played
        sorted_players = sorted(
            player_stats.items(), 
            key=lambda item: (
                item[1].get('wins', 0), 
                item[1].get('kills', 0),
                item[1].get('games_played', 0)
            ), 
            reverse=True
        )
        top_5_players = sorted_players[:5]

        # --- Canvas and Panel setup ---
        canvas_width, canvas_height = 854, 480
        panel_width, panel_height = 600, 350 # Increased width for new column
        
        panel_x = (canvas_width - panel_width) // 2
        panel_y = (canvas_height - panel_height) // 2

        # Image and drawing setup
        bg_color = (20, 20, 30, 220)
        border_color = (80, 80, 100, 255)
        title_color = (255, 255, 255, 255)
        header_color = (150, 150, 180, 255)
        text_color = (200, 200, 220, 255)
        value_color = (100, 200, 255, 255)
        shadow_color = (0, 0, 0, 100)
        radius = 15

        img = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Draw main panel
        draw.rounded_rectangle(
            (panel_x, panel_y, panel_x + panel_width, panel_y + panel_height), 
            fill=bg_color, radius=radius, outline=border_color, width=2
        )

        # Title
        title_text = "Top Players"
        title_bbox = draw.textbbox((0,0), title_text, font=scoreboard_font_title)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = panel_x + (panel_width - title_width) / 2
        title_y = panel_y + 20
        draw.text((title_x + 2, title_y + 2), title_text, font=scoreboard_font_title, fill=shadow_color)
        draw.text((title_x, title_y), title_text, font=scoreboard_font_title, fill=title_color)
        
        # Separator line
        draw.line(
            (panel_x + 20, panel_y + 70, panel_x + panel_width - 20, panel_y + 70), 
            fill=border_color, width=1
        )

        # Draw table headers
        header_y = panel_y + 85
        col_x_relative = {'rank': 40, 'name': 90, 'played': 350, 'wins': 470, 'kills': 560}
        headers = {
            "#": col_x_relative['rank'], 
            "Player": col_x_relative['name'], 
            "Played": col_x_relative['played'], 
            "Wins": col_x_relative['wins'], 
            "Kills": col_x_relative['kills']
        }
        
        for header, x_pos_rel in headers.items():
            x_pos_abs = panel_x + x_pos_rel
            bbox = draw.textbbox((0,0), header, font=scoreboard_font_text)
            header_width = bbox[2] - bbox[0]
            if header in ["Played", "Wins", "Kills"]: # Right align
                draw.text((x_pos_abs - header_width, header_y), header, font=scoreboard_font_text, fill=header_color)
            else: # Left align
                draw.text((x_pos_abs, header_y), header, font=scoreboard_font_text, fill=header_color)

        # Draw player rows
        row_y_start = panel_y + 125
        line_height = 40
        
        if not top_5_players:
             no_data_text = "No player data yet!"
             no_data_bbox = draw.textbbox((0,0), no_data_text, font=scoreboard_font_text)
             no_data_width = no_data_bbox[2] - no_data_bbox[0]
             no_data_x = panel_x + (panel_width - no_data_width) / 2
             no_data_y = panel_y + 180
             draw.text((no_data_x, no_data_y), no_data_text, font=scoreboard_font_text, fill=text_color)
        else:
            for i, (username, stats) in enumerate(top_5_players):
                y_pos = row_y_start + i * line_height
                rank = f"{i + 1}."
                display_name = (username[:12] + '..') if len(username) > 14 else username
                played = str(stats.get("games_played", 0))
                wins = str(stats.get("wins", 0))
                kills = str(stats.get("kills", 0))

                # Draw Rank & Name (left-aligned)
                draw.text((panel_x + col_x_relative['rank'], y_pos), rank, font=scoreboard_font_text, fill=text_color)
                draw.text((panel_x + col_x_relative['name'], y_pos), display_name, font=scoreboard_font_text, fill=value_color)
                
                # Draw stats (right-aligned)
                for stat_val, col_key in [(played, 'played'), (wins, 'wins'), (kills, 'kills')]:
                    bbox = draw.textbbox((0,0), stat_val, font=scoreboard_font_text)
                    stat_width = bbox[2] - bbox[0]
                    draw.text((panel_x + col_x_relative[col_key] - stat_width, y_pos), stat_val, font=scoreboard_font_text, fill=text_color)

        # Convert to data URL
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        base64_data = base64.b64encode(buffer.read()).decode('utf-8')
        return f"data:image/png;base64,{base64_data}"

    except Exception as e:
        print(f"Error generating scoreboard: {e}")
        traceback.print_exc()
        return None

# --- Main Utility Functions ---
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

def load_scoreboard_npc_location():
    global scoreboard_npc_location
    if os.path.exists(SCOREBOARD_NPC_FILE):
        with open(SCOREBOARD_NPC_FILE, 'r') as f: scoreboard_npc_location = json.load(f)

def save_scoreboard_npc_location():
    with open(SCOREBOARD_NPC_FILE, 'w') as f: json.dump(scoreboard_npc_location, f, indent=4)

def load_stats():
    global player_stats
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r') as f: player_stats = json.load(f)
    else:
        player_stats = {}

def save_stats():
    with open(STATS_FILE, 'w') as f: json.dump(player_stats, f, indent=4)

def get_player_stats(username):
    return player_stats.setdefault(username, {"wins": 0, "kills": 0, "games_played": 0})

def update_player_stat(username, stat, value_to_add):
    stats = get_player_stats(username)
    stats[stat] = stats.get(stat, 0) + value_to_add
    save_stats()

def load_font():
    global font, font_scaled, end_game_font, scoreboard_font_title, scoreboard_font_text
    font_size = 24
    end_font_size = 100
    sb_title_size = 30
    sb_text_size = 26
    try:
        # Main HUD Font
        if os.path.exists(FONT_FILE):
            font = ImageFont.truetype(FONT_FILE, font_size)
            font_scaled = ImageFont.truetype(FONT_FILE, font_size * 2)
            scoreboard_font_title = ImageFont.truetype(FONT_FILE, sb_title_size)
            scoreboard_font_text = ImageFont.truetype(FONT_FILE, sb_text_size)
        else:
            font = ImageFont.truetype("arial.ttf", font_size)
            font_scaled = ImageFont.truetype("arial.ttf", font_size * 2)
            scoreboard_font_title = ImageFont.truetype("arialbd.ttf", sb_title_size)
            scoreboard_font_text = ImageFont.truetype("arial.ttf", sb_text_size)
        
        # End Game Font
        if os.path.exists(END_GAME_FONT_FILE):
             end_game_font = ImageFont.truetype(END_GAME_FONT_FILE, end_font_size)
        else:
            end_game_font = ImageFont.truetype("arialbd.ttf", end_font_size)

    except IOError:
        font = ImageFont.load_default()
        font_scaled = ImageFont.load_default()
        end_game_font = ImageFont.load_default()
        scoreboard_font_title = ImageFont.load_default()
        scoreboard_font_text = ImageFont.load_default()


# --- Game Instance Class ---
class GameInstance:
    def __init__(self, game_id, server_api):
        self.game_id = game_id
        self.server_api = server_api
        self.game_state = "waiting"
        self.players = set()
        self.lobby_players = set()
        self.in_game_players = set()
        self.current_round = 0
        self.core_hp = config["core_hp"]
        self.active_zombies = {}
        self.next_zombie_id = self.game_id * 1000
        self.total_zombies_in_round = 0
        self.core_position = {}
        self.world_width = 120
        self.world_height = 80
        ground_y_tile = self.world_height // 2
        ground_y_pixel_top = ground_y_tile * TILE_SIZE
        self.ground_pixel_level = ground_y_pixel_top - (SKIN_HEIGHT // 2)
        self.world_data_cache = {}
        self.game_loop_task = None
        self.countdown_task = None

    def generate_world(self, is_game_world=False):
        world_key = "game" if is_game_world else "lobby"
        if world_key in self.world_data_cache:
            return self.world_data_cache[world_key]["json"]
        width, height = self.world_width, self.world_height
        world_data = [[-1 for _ in range(width)] for _ in range(height)]
        surface_y = height // 2
        if is_game_world:
            center_x = width // 2
            self.core_position = {"x": (center_x * TILE_SIZE) + (TILE_SIZE // 2), "y": ((surface_y - 1) * TILE_SIZE) + (TILE_SIZE // 2)}
            for x in range(width):
                world_data[surface_y][x] = 1
                for dy in range(1, 5):
                    if surface_y + dy < height: world_data[surface_y + dy][x] = 0
            world_data[surface_y - 1][center_x - 5] = 11
            world_data[surface_y - 1][center_x + 5] = 11
            world_data[surface_y - 1][center_x] = 12
        else: 
            for x in range(width):
                world_data[height - 10][x] = 2
                world_data[10][x] = 18
            for y in range(10, height - 9):
                world_data[y][0] = 2
                world_data[y][width - 1] = 2
            world_data[height - 11][10] = 15
            world_data[height - 11][width - 11] = 10
        world_json = json.dumps({"c2tilemap": True, "width": width, "height": height, "data": rle_encode(world_data, width, height)})
        self.world_data_cache[world_key] = {"grid": world_data, "json": world_json}
        return world_json

    async def add_player(self, username):
        if self.game_state not in ["waiting", "countdown"]:
            ws = self.server_api.get_websocket_from_username(username)
            if ws: await self.server_api.send_to_client(ws, "TELLRAW|PLACERSERVER|This game has already started.")
            return
        if len(self.players) >= config["max_players"]:
            ws = self.server_api.get_websocket_from_username(username)
            if ws: await self.server_api.send_to_client(ws, "TELLRAW|PLACERSERVER|This game is full.")
            return
        despawn_msg = f"{username}|-999|-999|Default|0|0|PLAYER_INFO"
        main_world_websockets = [ws for ws in self.server_api.get_connected_clients() if self.server_api.get_username_from_websocket(ws) not in player_to_game]
        if main_world_websockets:
            await asyncio.gather(*[ws.send(despawn_msg) for ws in main_world_websockets], return_exceptions=True)
        self.players.add(username)
        self.lobby_players.add(username)
        player_to_game[username] = self.game_id
        lobby_world_json = self.generate_world(is_game_world=False)
        await self.teleport_player(username, lobby_world_json, 2420, 2744)
        join_msg = f"TELLRAW|PLACERSERVER|{username} joined! ({len(self.players)}/{config['max_players']})"
        await self.broadcast_to_game_players(join_msg)
        if len(self.players) >= config["min_players"] and self.game_state == "waiting":
            self.start_countdown()
        elif len(self.players) == config["max_players"]:
            self.start_countdown()

    def start_countdown(self):
        if self.countdown_task and not self.countdown_task.done():
            self.countdown_task.cancel()
        async def countdown():
            try:
                self.game_state = "countdown"
                wait_time = config["countdown_full"] if len(self.players) == config["max_players"] else config["countdown_normal"]
                for i in range(wait_time, 0, -1):
                    if i <= 5:
                        await generate_and_broadcast_timer_image(self, i)
                    elif i % 5 == 0:
                         await self.broadcast_to_game_players(f"TELLRAW|PLACERSERVER|Game starting in {i}...")
                    await asyncio.sleep(1)
                
                await self.broadcast_to_game_players("HIDE_IMAGE|PLACERSERVER|")

                if self.game_state == "countdown" and len(self.players) >= config["min_players"]:
                     await self.start_game()
                elif self.game_state == "countdown":
                    self.game_state = "waiting"
                    await self.broadcast_to_game_players("TELLRAW|PLACERSERVER|Not enough players to start. Countdown cancelled.")
            except asyncio.CancelledError:
                self.game_state = "waiting"
                await self.broadcast_to_game_players("TELLRAW|PLACERSERVER|Countdown cancelled.")
                await self.broadcast_to_game_players("HIDE_IMAGE|PLACERSERVER|")

        self.countdown_task = asyncio.create_task(countdown())

    async def start_game(self):
        self.game_state = "playing"
        self.current_round = 0
        self.core_hp = config["core_hp"]
        self.in_game_players = self.lobby_players.copy()
        self.lobby_players.clear()
        
        # Update Games Played stat for all players starting
        for username in self.in_game_players:
            update_player_stat(username, "games_played", 1)
        
        await self.broadcast_to_game_players("KILL_LOG|PLACERSERVER|")
        
        game_world_json = self.generate_world(is_game_world=True)
        for username in self.in_game_players:
            await self.teleport_player(username, game_world_json, 2413, 1504)
        await self.broadcast_to_game_players("TELLRAW|PLACERSERVER|GAME STARTED! Defend the core!")
        if self.game_loop_task: self.game_loop_task.cancel()
        self.game_loop_task = asyncio.create_task(self.game_loop())

    async def game_loop(self):
        while self.game_state == "playing":
            try:
                if not self.active_zombies:
                    if self.current_round >= config["max_rounds"]:
                        self.end_game(victory=True)
                        return

                    self.current_round += 1
                    await self.broadcast_to_game_players(f"TELLRAW|PLACERSERVER|ROUND {self.current_round} INCOMING!")
                    await self.spawn_zombie_round()
                    await asyncio.sleep(3)

                zombies_to_remove = []
                for zid, zombie in list(self.active_zombies.items()):
                    if zombie["y"] < self.ground_pixel_level:
                        zombie["y"] += config["zombie_gravity"]
                        if zombie["y"] > self.ground_pixel_level:
                            zombie["y"] = self.ground_pixel_level
                    else:
                        zombie["y"] = self.ground_pixel_level
                        dx = self.core_position["x"] - zombie["x"]
                        if abs(dx) > (TILE_SIZE / 2):
                            if dx > 0: zombie["x"] += config["zombie_speed"]
                            else: zombie["x"] -= config["zombie_speed"]
                        elif not zombie.get("is_minion", False):
                            self.core_hp -= 1
                            if self.core_hp % 20 == 0:
                                await self.broadcast_to_game_players(f"TELLRAW|PLACERSERVER|Core HP: {self.core_hp}/{config['core_hp']}")
                            if self.core_hp <= 0:
                                self.end_game(victory=False)
                                return
                    
                    if zombie["hp"] <= 0:
                        zombies_to_remove.append(zid)
                
                if zombies_to_remove:
                    for zid in zombies_to_remove:
                        if zid in self.active_zombies:
                            zombie = self.active_zombies.pop(zid)
                            killer = zombie.get("last_hit_by")
                            if killer and not zombie.get("is_minion", False):
                                update_player_stat(killer, "kills", 1)
                            await self.broadcast_to_game_players(f"{zombie['name']}|-999|-999|Default|0|0|PLAYER_INFO")
                    await generate_and_broadcast_hud(self)
                
                if not self.in_game_players and self.game_state == "playing":
                    self.end_game(victory=False)
                    return
                for zid, zombie in self.active_zombies.items():
                    skin = "Steve" if zombie.get("is_master", False) else "LAG"
                    msg = f"{zombie['name']}|{int(zombie.get('x', -999))}|{int(zombie.get('y', -999))}|{skin}|{zid}|{zombie['hp']}|PLAYER_INFO"
                    await self.broadcast_to_game_players(msg)
                await asyncio.sleep(1/20)
            except asyncio.CancelledError: break
            except Exception as e:
                self.server_api.log(f"ZombiesGame (ID {self.game_id}): Error in game loop: {e}"); traceback.print_exc()

    async def spawn_zombie_round(self):
        num_zombies = config["zombies_per_round_base"] + (self.current_round - 1) * config["zombies_increase_per_round"]
        self.total_zombies_in_round = num_zombies
        zombie_hp = config["zombie_hp_base"] + (self.current_round - 1) * config["zombie_hp_increase_per_round"]
        
        await self.spawn_zombie(is_master=True, hp=zombie_hp * config["master_zombie_hp_multiplier"])
        await asyncio.sleep(0.1)
        for _ in range(num_zombies - 1):
            await self.spawn_zombie(hp=zombie_hp)
            await asyncio.sleep(0.1)
        
        await generate_and_broadcast_hud(self)


    async def spawn_zombie(self, hp, is_master=False):
        zid = self.next_zombie_id; self.next_zombie_id += 1
        spawn_side = random.choice([-1, 1])
        spawn_offset = 5 + 4 + random.randint(0, 2)
        spawn_tile_x = (self.world_width // 2) + (spawn_side * spawn_offset)
        zombie_name = f"Master Zombie-{zid}" if is_master else f"Zombie-{zid}"
        zombie_data = {
            "name": zombie_name, "x": (spawn_tile_x * TILE_SIZE) + (TILE_SIZE // 2),
            "y": self.ground_pixel_level - (SKIN_HEIGHT * 2), "hp": hp, "is_master": is_master,
            "last_hit_by": None
        }
        self.active_zombies[zid] = zombie_data

    def end_game(self, victory=False):
        if self.game_state == "ended": return
        self.game_state = "ended"
        asyncio.create_task(self._end_game_task(victory))

    async def _end_game_task(self, victory=False):
        global active_games, player_to_game
        if self.game_loop_task: self.game_loop_task.cancel()
        if self.countdown_task: self.countdown_task.cancel()
        
        try:
            await self.broadcast_to_game_players("HIDE_IMAGE|PLACERSERVER|")
            await asyncio.sleep(0.1) 

            if victory:
                await generate_end_game_image(self, "VICTORY!", (255, 215, 0, 255))
                # Update wins for all players still in the game
                for username in self.in_game_players:
                    update_player_stat(username, "wins", 1)
            else:
                await generate_end_game_image(self, "DEFEATED!", (255, 0, 0, 255))

            for zid, zombie in list(self.active_zombies.items()):
                await self.broadcast_to_game_players(f"{zombie['name']}|-999|-999|Default|0|0|PLAYER_INFO")
            self.active_zombies.clear()
            
            await asyncio.sleep(5)
            await self.broadcast_to_game_players("HIDE_IMAGE|PLACERSERVER|")

            lobby_pos = config.get("lobby_location", {"x": 461, "y": 1104})
            main_world_json = "{}"
            try:
                with open("worlds/world.pw", 'r') as f: main_world_json = f.read()
            except Exception as e:
                self.server_api.log(f"ZombiesGame (ID {self.game_id}): CRITICAL ERROR! Failed to load 'worlds/world.pw'. Error: {e}")

            players_to_teleport = list(self.players)
            for username in players_to_teleport:
                if username in player_to_game: del player_to_game[username]
                await self.teleport_player(username, main_world_json, lobby_pos['x'], lobby_pos['y'])
            
            self.players.clear(); self.in_game_players.clear(); self.lobby_players.clear()
            if self.game_id in active_games: del active_games[self.game_id]
            
            if not active_games:
                self.server_api.clear_broadcast_override()
                self.server_api.log("ZombiesGame: Last game ended, broadcast override released.")
        except Exception as e:
            self.server_api.log(f"ZombiesGame (ID {self.game_id}): CRITICAL ERROR in _end_game_task: {e}")
            traceback.print_exc()


    async def teleport_player(self, username, world_json, pixel_x, pixel_y):
        ws = self.server_api.get_websocket_from_username(username)
        if ws:
            await self.server_api.send_to_client(ws, f"WORLD_DATA|PLACERSERVER|{world_json}")
            await asyncio.sleep(0.1)
            await self.server_api.send_to_client(ws, f"SET_POSITION|PLACERSERVER|{pixel_x}|{pixel_y}|{username}")
    
    async def broadcast_to_game_players(self, message):
        for username in list(self.players):
            ws = self.server_api.get_websocket_from_username(username)
            if ws:
                try: await self.server_api.send_to_client(ws, message)
                except Exception as e: self.server_api.log(f"ZombiesGame (ID {self.game_id}): Failed to send message to {username}: {e}")

    async def remove_player(self, username):
        self.players.discard(username); self.lobby_players.discard(username); self.in_game_players.discard(username)
        if username in player_to_game: del player_to_game[username]
        despawn_msg = f"{username}|-999|-999|Default|0|0|PLAYER_INFO"
        await self.broadcast_to_game_players(despawn_msg)
        leave_msg = f"TELLRAW|PLACERSERVER|{username} left the game. ({len(self.players)}/{config['max_players']})"
        await self.broadcast_to_game_players(leave_msg)
        if self.game_state == "countdown" and len(self.players) < config["min_players"]:
            if self.countdown_task and not self.countdown_task.done(): self.countdown_task.cancel()
        if not self.players and self.game_state != "ended":
            self.end_game(victory=False)

# --- RLE Encoder (helper) ---
def rle_encode(grid, width, height):
    parts = []; current_id = None; count = 0
    for y in range(height):
        for x in range(width):
            block_id = grid[y][x]
            if current_id is None: current_id = block_id; count = 1
            elif block_id == current_id: count += 1
            else:
                parts.append(f"{count}x{current_id}" if count > 1 else str(current_id))
                current_id = block_id; count = 1
    if current_id is not None: parts.append(f"{count}x{current_id}" if count > 1 else str(current_id))
    return ",".join(parts)

# --- Global Broadcast and Plugin Hooks ---
async def minigame_broadcast_override(server_api, message, exclude_websocket=None):
    """
    This function intercepts all server broadcasts.
    It directs messages to the correct scope: either the main world or a specific game instance.
    """
    try:
        parts = message.split('|'); msg_type = parts[0]; sender_username = None

        # --- Identify the sender of the message ---
        if msg_type == "PLAYER_INFO" or msg_type.endswith("PLAYER_INFO"):
            sender_username = parts[0]
        elif msg_type == "PLAYER_MESSAGE": # BUG FIX: Correctly identify chat message sender
            sender_username = parts[2]
        elif exclude_websocket:
            sender_username = server_api.get_username_from_websocket(exclude_websocket)
        
        # --- Route the message ---
        sender_game_id = player_to_game.get(sender_username)
        if sender_game_id is not None:
            # Sender is in a game, broadcast to their game instance
            game = active_games.get(sender_game_id)
            if game:
                targets = [server_api.get_websocket_from_username(p) for p in game.players if server_api.get_websocket_from_username(p) != exclude_websocket]
                if targets:
                    await asyncio.gather(*[ws.send(message) for ws in targets if ws], return_exceptions=True)
        else:
            # Sender is in the main world, broadcast to other main world players
            main_world_websockets = [
                ws for ws in server_api.get_connected_clients() 
                if server_api.get_username_from_websocket(ws) not in player_to_game and ws != exclude_websocket
            ]
            if main_world_websockets:
                await asyncio.gather(*[ws.send(message) for ws in main_world_websockets], return_exceptions=True)
    except Exception as e:
        server_api.log(f"ZombiesGame: CRITICAL ERROR in broadcast override: {e}"); traceback.print_exc()

async def global_periodic_broadcast(server_api):
    global last_npc_name, last_scoreboard_npc_name
    while True:
        try:
            # --- Main Join NPC ---
            # BUG FIX: Count all players in any game instance, not just lobbies.
            total_players = sum(len(game.players) for game in active_games.values())
            npc_name = f"Zombies ({total_players} Players)"
            
            main_world_websockets = [ws for ws in server_api.get_connected_clients() if server_api.get_username_from_websocket(ws) and server_api.get_username_from_websocket(ws) not in player_to_game]
            
            if npc_name != last_npc_name and last_npc_name:
                 despawn_msg = f"{last_npc_name}|-999|-999|Default|0|0|PLAYER_INFO"
                 if main_world_websockets:
                     await asyncio.gather(*[ws.send(despawn_msg) for ws in main_world_websockets], return_exceptions=True)
            
            if npc_location:
                msg = f"{npc_name}|{int(npc_location['x'])}|{int(npc_location['y'])}|{npc_location.get('skin', 'GameNPC')}|999|100|PLAYER_INFO"
                last_npc_name = npc_name
                if main_world_websockets:
                    await asyncio.gather(*[ws.send(msg) for ws in main_world_websockets], return_exceptions=True)

            # --- Scoreboard NPC ---
            scoreboard_npc_name = "Zombies Stats"
            if scoreboard_npc_name != last_scoreboard_npc_name and last_scoreboard_npc_name:
                despawn_msg = f"{last_scoreboard_npc_name}|-999|-999|Default|0|0|PLAYER_INFO"
                if main_world_websockets:
                     await asyncio.gather(*[ws.send(despawn_msg) for ws in main_world_websockets], return_exceptions=True)

            if scoreboard_npc_location:
                msg = f"{scoreboard_npc_name}|{int(scoreboard_npc_location['x'])}|{int(scoreboard_npc_location['y'])}|{scoreboard_npc_location.get('skin', 'GameNPC')}|998|100|PLAYER_INFO"
                last_scoreboard_npc_name = scoreboard_npc_name
                if main_world_websockets:
                    await asyncio.gather(*[ws.send(msg) for ws in main_world_websockets], return_exceptions=True)


            await asyncio.sleep(1)
        except asyncio.CancelledError: break
        except Exception as e: server_api.log(f"ZombiesGame: Error in global broadcast: {e}")

def on_load(server_api):
    global global_broadcast_task
    server_api.log("ZombiesGame Plugin: Loading...")
    load_config()
    load_npc_location()
    load_scoreboard_npc_location()
    load_stats()
    load_font()
    if global_broadcast_task: global_broadcast_task.cancel()
    global_broadcast_task = asyncio.create_task(global_periodic_broadcast(server_api))
    server_api.log("ZombiesGame Plugin: Loaded successfully!")

def on_unload(server_api):
    global global_broadcast_task
    if global_broadcast_task: global_broadcast_task.cancel()
    for game in list(active_games.values()):
        game.end_game(victory=False)
    if active_games: server_api.clear_broadcast_override()
    server_api.log("ZombiesGame Plugin: Unloaded.")

async def on_connect(websocket, server_api):
    # Send join NPC info
    if npc_location:
        total_players = sum(len(game.players) for game in active_games.values())
        npc_name = f"Zombies ({total_players} Players)"
        msg = f"{npc_name}|{int(npc_location['x'])}|{int(npc_location['y'])}|{npc_location.get('skin', 'GameNPC')}|999|100|PLAYER_INFO"
        await server_api.send_to_client(websocket, msg)
    # Send scoreboard NPC info
    if scoreboard_npc_location:
        msg = f"Zombies Stats|{int(scoreboard_npc_location['x'])}|{int(scoreboard_npc_location['y'])}|{scoreboard_npc_location.get('skin', 'GameNPC')}|998|100|PLAYER_INFO"
        await server_api.send_to_client(websocket, msg)


async def on_message(websocket, message_string, message_parts, server_api):
    global player_locations, next_game_id, config
    if len(message_parts) >= 3 and message_parts[1] == "SYNC_REQ":
        username = message_parts[0]
        if username in player_to_game:
            server_api.log(f"ZombiesGame: Found and removed ghost session for {username}.")
            old_game_id = player_to_game[username]
            if old_game_id in active_games:
                await active_games[old_game_id].remove_player(username)
            if username in player_to_game:
                 del player_to_game[username]
    if len(message_parts) >= 7 and message_parts[6] == "PLAYER_INFO":
        username = message_parts[0]
        try:
            if username not in player_to_game:
                player_locations[username] = {"x": int(message_parts[1]), "y": int(message_parts[2])}
        except (ValueError, IndexError): pass

    if len(message_parts) >= 4 and message_parts[0] == "PLAYER_MESSAGE" and message_parts[1] == "PLACERCLIENT":
        username = message_parts[2]
        command = message_parts[3].strip()
        
        if command == "!zombies_spawn_npc":
            if username in player_locations and username not in player_to_game:
                global npc_location
                npc_location = {"x": player_locations[username]["x"], "y": player_locations[username]["y"], "skin": "GameNPC"}
                save_npc_location()
                await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Zombies Game NPC spawned at your location.")
            else:
                await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Your location is not yet known or you are in-game. Please move in the main world first.")
            return True

        if command == "!zombies_sb_npc": # NEW FEATURE
            if username in player_locations and username not in player_to_game:
                global scoreboard_npc_location
                scoreboard_npc_location = {"x": player_locations[username]["x"], "y": player_locations[username]["y"], "skin": "GameNPC"}
                save_scoreboard_npc_location()
                await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Zombies scoreboard NPC spawned at your location.")
            else:
                await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Your location is not yet known or you are in-game. Please move in the main world first.")
            return True

        if command == "!set_lobby":
            if username in player_locations and username not in player_to_game:
                config["lobby_location"] = {"x": player_locations[username]["x"], "y": player_locations[username]["y"]}
                save_config()
                await server_api.send_to_client(websocket, f"TELLRAW|PLACERSERVER|Main lobby location set to {config['lobby_location']['x']}, {config['lobby_location']['y']}.")
            else:
                 await server_api.send_to_client(websocket, "TELLRAW|PLACERSERVER|Your location is not yet known or you are in-game. Please move in the main world first.")
            return True


    # --- Player Actions (Damage) ---
    if len(message_parts) == 4 and message_parts[0] == "DAMAGE" and message_parts[1] == "PLACERCLIENT":
        target_name = message_parts[2]
        username = message_parts[3]

        # Handle clicking the SCOREBOARD NPC
        if target_name.startswith("Zombies Stats"):
            async def show_and_hide_scoreboard():
                image_data = await generate_scoreboard_image() # Changed: No longer needs username
                if image_data:
                    await server_api.send_to_client(websocket, f"SHOW_IMAGE|PLACERSERVER|{image_data}")
                    await asyncio.sleep(5)
                    await server_api.send_to_client(websocket, "HIDE_IMAGE|PLACERSERVER|")
            asyncio.create_task(show_and_hide_scoreboard())
            return True

        # Handle clicking the JOIN NPC
        if target_name.startswith("Zombies"):
            if username in player_to_game: return True
            target_game = None
            for game in active_games.values():
                if game.game_state in ["waiting", "countdown"] and len(game.players) < config["max_players"]:
                    target_game = game
                    break
            if target_game is None:
                if not active_games:
                    override_func = functools.partial(minigame_broadcast_override, server_api)
                    server_api.set_broadcast_override(override_func)
                    server_api.log("ZombiesGame: First game created, broadcast override is active.")
                target_game = GameInstance(next_game_id, server_api)
                active_games[next_game_id] = target_game
                next_game_id += 1
            await target_game.add_player(username)
            return True
        
        # Handle damaging a ZOMBIE
        if target_name.startswith("Zombie-") or target_name.startswith("Master Zombie-"):
            if username in player_to_game:
                game_id = player_to_game[username]
                game = active_games.get(game_id)
                if game and username in game.in_game_players:
                    for zid, zdata in list(game.active_zombies.items()):
                        if zdata["name"] == target_name:
                            zdata["hp"] -= 10
                            zdata["last_hit_by"] = username # Track who hit the zombie
                            break
            return True

    return False

async def on_disconnect(websocket, server_api):
    username = server_api.get_username_from_websocket(websocket)
    if username and username in player_to_game:
        game_id = player_to_game[username]
        game = active_games.get(game_id)
        if game:
            await game.remove_player(username)
    if username and username in player_locations:
        del player_locations[username]
