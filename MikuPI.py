# MikuPI.py
# Plasocket plugin for world generation and info, with multiple world types,
# using a specific user-defined block palette.

import os
import random
import uuid
import asyncio 
import json 
import traceback 
import math 

# --- User-Defined Block IDs ---
BLOCK_IDS = {
    "AIR": -1,
    "DIRT": 0,
    "GRASS": 1,            # Grass Block
    "STONE": 2,
    "SAND": 3,
    "WOOD_LOG": 4,         # Wood (with lines on it)
    "PLANKS": 5,           # Planks (with no lines on it)
    "HOLLOW_PLANKS": 6,
    "HOLLOW_STONE": 7,
    "HOLLOW_DIRT": 8,
    "COPPER": 9,
    "EMERALD": 10,
    "RUBY": 11,
    "DIAMOND": 12,
    "IRON": 13,            # Can be used as snow
    "GIFTED_CHEST": 14,
    "GOLD": 15,
    "PURPLE_BLOCK": 16,    # Purple
    "ORANGE_BLOCK": 17,    # Orange
    "GREEN_BLOCK": 18,     # Green (will be used for leaves)
    "RED_BLOCK": 19,       # Red
    "LIGHT_BLUE_BLOCK": 20,# Light Blue (will be used for water/ice)
    "DARK_BLUE_BLOCK": 21, # Dark Blue
    "TNT_BLOCK": 22,       # TNT
    "WHITE_CHEST": 23,
    "YELLOW_CHEST": 24,
    "GRAY_CHEST": 25,
    "GREEN_CHEST": 26,
    "BLUE_CHEST": 27,
    # --- Mappings for previously used concepts ---
    "LEAVES": 18,          # Mapped to GREEN_BLOCK
    "WATER": 20,           # Mapped to LIGHT_BLUE_BLOCK
    "ICE": 20,             # Mapped to LIGHT_BLUE_BLOCK (as per user using Iron for snow)
    "SNOW_BLOCK": 13,      # Mapped to IRON
    "OBSIDIAN": 2,         # Mapped to STONE (as a dark rock, or use GRAY_CHEST if preferred)
    "LAVA": 19,            # Mapped to RED_BLOCK
    "CRYSTAL_1": 16,       # Mapped to PURPLE_BLOCK for "Crystal Caverns"
    "CRYSTAL_2": 21,       # Mapped to DARK_BLUE_BLOCK for "Crystal Caverns"
}

# --- World Generation Parameters ---
DEFAULT_WIDTH = 200
DEFAULT_HEIGHT = 100
MIN_WIDTH = 30 
MAX_WIDTH = 600 
MIN_HEIGHT = 30
MAX_HEIGHT = 400 

PLUGIN_DATA_DIR = "plugins/MikuPI" 

# --- World Type Definitions ---
WORLD_TYPES = {
    1: {
        "name": "Normal World",
        "description": "A balanced world with varied terrain, trees (green blocks), caves, and standard resources.",
        "params": {"is_flat": False, "has_trees": True, "cave_density_factor": 1.0, "resource_multiplier": 1.0, "sky_proportion": 0.3, "dirt_thickness": 3, "terrain_variation": 1, "surface_block": BLOCK_IDS["GRASS"], "leaf_block": BLOCK_IDS["GREEN_BLOCK"], "water_block": BLOCK_IDS["LIGHT_BLUE_BLOCK"]}
    },
    2: {
        "name": "Flat Barren Lands",
        "description": "A mostly flat world with minimal vegetation (no trees) and scarce resources.",
        "params": {"is_flat": True, "has_trees": False, "cave_density_factor": 0.1, "resource_multiplier": 0.2, "sky_proportion": 0.35, "dirt_thickness": 2, "surface_block": BLOCK_IDS["DIRT"], "sub_surface_block": BLOCK_IDS["STONE"]}
    },
    3: {
        "name": "Sky Islands",
        "description": "Floating islands in a vast sky, with some trees (green blocks).",
        "params": {"is_flat": False, "has_trees": True, "cave_density_factor": 0.5, "resource_multiplier": 0.8, "sky_proportion": 0.7, "dirt_thickness": 3, "terrain_algorithm": "sky_islands", "leaf_block": BLOCK_IDS["GREEN_BLOCK"], "surface_block": BLOCK_IDS["GRASS"]}
    },
    4: {
        "name": "Deep & Vast Caves",
        "description": "A world dominated by extensive cave systems, rich in underground resources.",
        "params": {"is_flat": False, "has_trees": True, "cave_density_factor": 3.0, "resource_multiplier": 1.5, "sky_proportion": 0.25, "dirt_thickness": 4, "cave_size_multiplier": 1.5, "leaf_block": BLOCK_IDS["GREEN_BLOCK"], "surface_block": BLOCK_IDS["GRASS"]}
    },
    5: {
        "name": "Resource Heaven",
        "description": "Abundant ores of all types, making mining very rewarding.",
        "params": {"is_flat": False, "has_trees": True, "cave_density_factor": 1.0, "resource_multiplier": 3.0, "sky_proportion": 0.3, "dirt_thickness": 3, "leaf_block": BLOCK_IDS["GREEN_BLOCK"], "surface_block": BLOCK_IDS["GRASS"]}
    },
    6: {
        "name": "Frozen Tundra",
        "description": "A cold world with iron 'snow' plains and light blue 'ice' waters.",
        "params": {"is_flat": False, "has_trees": True, "tree_type": "sparse_pine", "cave_density_factor": 0.7, "resource_multiplier": 0.9, "sky_proportion": 0.3, "dirt_thickness": 2, "surface_block": BLOCK_IDS["IRON"], "sub_surface_block": BLOCK_IDS["DIRT"], "main_stone_block": BLOCK_IDS["STONE"], "water_block": BLOCK_IDS["LIGHT_BLUE_BLOCK"], "leaf_block": BLOCK_IDS["GREEN_BLOCK"]}
    },
    7: {
        "name": "Desert Oasis",
        "description": "Vast sandy deserts with occasional oases of light blue water and palm-like trees.",
        "params": {"is_flat": True, "terrain_variation": 0.5, "has_trees": True, "tree_type": "palm", "cave_density_factor": 0.3, "resource_multiplier": 0.7, "sky_proportion": 0.3, "dirt_thickness": 1, "surface_block": BLOCK_IDS["SAND"], "sub_surface_block": BLOCK_IDS["SAND"], "main_stone_block": BLOCK_IDS["STONE"], "water_block": BLOCK_IDS["LIGHT_BLUE_BLOCK"], "feature_oases": True, "leaf_block": BLOCK_IDS["GREEN_BLOCK"]} 
    },
    8: {
        "name": "Scorched Lands", # Renamed from Volcanic Wasteland
        "description": "A harsh landscape of stone and red/orange 'lava' pools.",
        "params": {"is_flat": False, "terrain_variation": 2, "has_trees": False, "cave_density_factor": 0.5, "resource_multiplier": 0.5, "sky_proportion": 0.2, "dirt_thickness": 1, "surface_block": BLOCK_IDS["STONE"], "sub_surface_block": BLOCK_IDS["STONE"], "main_stone_block": BLOCK_IDS["STONE"], "water_block": BLOCK_IDS["RED_BLOCK"], "feature_lava_pools": True} # Using RED_BLOCK for lava
    },
    9: {
        "name": "Floating Forests",
        "description": "Islands of earth held aloft by massive trees (green blocks), bridging a cloudy abyss.",
        "params": {"is_flat": False, "has_trees": True, "tree_type": "giant", "cave_density_factor": 0.2, "resource_multiplier": 0.7, "sky_proportion": 0.65, "dirt_thickness": 4, "terrain_algorithm": "sky_islands", "island_density": 0.5, "leaf_block": BLOCK_IDS["GREEN_BLOCK"], "surface_block": BLOCK_IDS["GRASS"]}
    },
    10: {
        "name": "Colorful Caverns", # Renamed from Crystal Caverns
        "description": "Underground world shimmering with purple and dark blue blocks, some rare ores.",
        "params": {"is_flat": False, "has_trees": False, "cave_density_factor": 2.0, "resource_multiplier": 1.2, "sky_proportion": 0.15, "dirt_thickness": 2, "feature_colored_stones": True, "main_stone_block": BLOCK_IDS["STONE"]}
    },
    11: {
        "name": "Oceanic World",
        "description": "A world largely covered by light blue water, with scattered small sandy islands.",
        "params": {"is_flat": True, "has_trees": True, "tree_type":"palm_small", "cave_density_factor": 0.3, "resource_multiplier": 0.6, "sky_proportion": 0.3, "dirt_thickness": 2, "water_level_y": int(DEFAULT_HEIGHT * 0.6), "surface_block": BLOCK_IDS["SAND"], "main_stone_block": BLOCK_IDS["STONE"], "water_block": BLOCK_IDS["LIGHT_BLUE_BLOCK"], "leaf_block": BLOCK_IDS["GREEN_BLOCK"]}
    },
    12: {
        "name": "Mountainous Highlands",
        "description": "Dominated by tall peaks and deep valleys, with sparse trees (green blocks).",
        "params": {"is_flat": False, "has_trees": True, "tree_type":"pine", "cave_density_factor": 0.8, "resource_multiplier": 1.1, "sky_proportion": 0.2, "dirt_thickness": 2, "terrain_variation": 3, "mountain_frequency": 0.7, "leaf_block": BLOCK_IDS["GREEN_BLOCK"], "surface_block": BLOCK_IDS["GRASS"]}
    },
    13: {
        "name": "Rainbow Fields",
        "description": "A vibrant world with colorful striped terrain using new colored blocks.",
        "params": {"is_flat": False, "has_trees": True, "tree_density": 0.03, "cave_density_factor": 0.5, "resource_multiplier": 0.5, "sky_proportion": 0.35, "dirt_thickness": 1, "terrain_algorithm": "rainbow_stripes", "leaf_block": BLOCK_IDS["GREEN_BLOCK"]}
    },
    14: {
        "name": "TNT Hazard Zone",
        "description": "Looks normal, but TNT is hidden within the stone! Be careful.",
        "params": {"is_flat": False, "has_trees": True, "cave_density_factor": 1.0, "resource_multiplier": 1.0, "sky_proportion": 0.3, "dirt_thickness": 3, "feature_tnt_sprinkle": True, "tnt_chance": 0.01, "leaf_block": BLOCK_IDS["GREEN_BLOCK"], "surface_block": BLOCK_IDS["GRASS"]} 
    },
    15: {
        "name": "Gemstone Collector's Dream",
        "description": "Rich in all ores and colorful 'gemstone' blocks (purple, orange, etc.).",
        "params": {"is_flat": False, "has_trees": True, "cave_density_factor": 1.2, "resource_multiplier": 2.5, "sky_proportion": 0.25, "dirt_thickness": 3, "feature_gem_blocks": True, "gem_block_chance": 0.02, "leaf_block": BLOCK_IDS["GREEN_BLOCK"], "surface_block": BLOCK_IDS["GRASS"]}
    }
}


# --- Helper: Run-Length Encoder ---
def rle_encode(world_grid, width, height):
    data_parts = []
    if not world_grid or (height > 0 and not world_grid[0]):
        return ""
    current_id = None
    count = 0
    for y in range(height):
        for x in range(width):
            try:
                block_id = world_grid[y][x]
            except IndexError:
                print(f"[MikuPI Plugin] RLE Error: Index out of bounds at ({x},{y}). Treating as AIR.")
                block_id = BLOCK_IDS["AIR"]
            if current_id is None:
                current_id = block_id
                count = 1
            elif block_id == current_id:
                count += 1
            else:
                if count == 1:
                    data_parts.append(str(current_id))
                else:
                    data_parts.append(f"{count}x{current_id}")
                current_id = block_id
                count = 1
    if current_id is not None:
        if count == 1:
            data_parts.append(str(current_id))
        else:
            data_parts.append(f"{count}x{current_id}")
    return ",".join(data_parts)

# --- Helper: World Generation Logic (now parameterized) ---
def _generate_world_grid_internal(width, height, gen_params):
    grid = [[BLOCK_IDS["AIR"] for _ in range(width)] for _ in range(height)]
    
    sky_prop = gen_params.get("sky_proportion", 0.30)
    dirt_thick = gen_params.get("dirt_thickness", 3)
    is_flat = gen_params.get("is_flat", False)
    has_trees = gen_params.get("has_trees", True)
    cave_factor = gen_params.get("cave_density_factor", 1.0)
    resource_factor = gen_params.get("resource_multiplier", 1.0)
    terrain_variation_factor = gen_params.get("terrain_variation", 1) 
    surface_block_override = gen_params.get("surface_block", BLOCK_IDS["GRASS"])
    sub_surface_block_override = gen_params.get("sub_surface_block", BLOCK_IDS["DIRT"])
    main_stone_override = gen_params.get("main_stone_block", BLOCK_IDS["STONE"])
    water_block_override = gen_params.get("water_block", BLOCK_IDS["LIGHT_BLUE_BLOCK"]) # Default to light blue
    water_level_y_override = gen_params.get("water_level_y", -1) 
    terrain_algorithm = gen_params.get("terrain_algorithm", "default")
    leaf_block_override = gen_params.get("leaf_block", BLOCK_IDS["GREEN_BLOCK"]) # Default leaves

    min_sky_blocks = 5
    min_underground_blocks = 15 + dirt_thick 
    
    calculated_surface_y = int(height * sky_prop)
    ground_surface_start_y = max(min_sky_blocks, min(height - min_underground_blocks, calculated_surface_y))
    
    surface_y_coords = [ground_surface_start_y] * width

    # Terrain Profile
    if terrain_algorithm == "sky_islands":
        island_density = gen_params.get("island_density", 0.3)
        min_island_y = int(height * 0.1)
        max_island_y = int(height * (sky_prop - 0.1)) 
        island_min_width, island_max_width = 5, 20
        island_min_height, island_max_height = 3, 8

        for _ in range(int(width * height * 0.005 * island_density)): 
            ix = random.randint(0, width - 1)
            iy = random.randint(min_island_y, max_island_y)
            iw = random.randint(island_min_width, island_max_width)
            ih = random.randint(island_min_height, island_max_height)
            
            for y_offset in range(ih):
                for x_offset in range(iw):
                    cur_x, cur_y = ix + x_offset - iw // 2, iy + y_offset
                    if 0 <= cur_x < width and 0 <= cur_y < height:
                        if y_offset == 0: 
                            grid[cur_y][cur_x] = surface_block_override
                        elif y_offset < dirt_thick:
                            grid[cur_y][cur_x] = sub_surface_block_override
                        else:
                            grid[cur_y][cur_x] = main_stone_override
            for i in range(ix - iw//2, ix + iw//2 +1):
                if 0 <= i < width:
                    surface_y_coords[i] = min(surface_y_coords[i], iy)


    elif terrain_algorithm == "rainbow_stripes":
        stripe_colors = [BLOCK_IDS["RED_BLOCK"], BLOCK_IDS["ORANGE_BLOCK"], BLOCK_IDS["GREEN_BLOCK"], BLOCK_IDS["DARK_BLUE_BLOCK"], BLOCK_IDS["PURPLE_BLOCK"], BLOCK_IDS["LIGHT_BLUE_BLOCK"]]
        for x in range(width):
            if not is_flat and x > 0:
                variation = random.randint(-terrain_variation_factor, terrain_variation_factor)
                surface_y_coords[x] = max(1, min(height - dirt_thick - 10, surface_y_coords[x-1] + variation))
            else:
                surface_y_coords[x] = ground_surface_start_y
            
            sy = surface_y_coords[x]
            current_surface_block = stripe_colors[ (x // gen_params.get("stripe_width", 5)) % len(stripe_colors) ]

            if 0 <= sy < height: grid[sy][x] = current_surface_block
            for i in range(1, dirt_thick + 1):
                dirt_y = sy + i
                if 0 <= dirt_y < height: grid[dirt_y][x] = sub_surface_block_override
                else: break 
            stone_start_y = sy + dirt_thick + 1
            for y_stone in range(stone_start_y, height):
                if 0 <= y_stone < height: grid[y_stone][x] = main_stone_override
    else: # Default terrain generation
        for x in range(width):
            if not is_flat and x > 0:
                variation = random.randint(-terrain_variation_factor, terrain_variation_factor)
                surface_y_coords[x] = max(1, min(height - dirt_thick - 10, surface_y_coords[x-1] + variation))
            else:
                surface_y_coords[x] = ground_surface_start_y
            
            sy = surface_y_coords[x]
            
            stone_fill_end = sy + dirt_thick + 1
            for y_fill_stone in range(height -1, stone_fill_end -1, -1):
                if 0 <= y_fill_stone < height: grid[y_fill_stone][x] = main_stone_override
            for i in range(1, dirt_thick + 1):
                dirt_y = sy + i
                if 0 <= dirt_y < height: grid[dirt_y][x] = sub_surface_block_override
                else: break 
            if 0 <= sy < height: grid[sy][x] = surface_block_override

    # Water Level
    if water_level_y_override != -1:
        for y_water in range(water_level_y_override, height):
            for x_water in range(width):
                if 0 <= y_water < height and 0 <= x_water < width:
                    if grid[y_water][x_water] == BLOCK_IDS["AIR"] or \
                       (y_water < surface_y_coords[x_water] and grid[y_water][x_water] != BLOCK_IDS["WOOD_LOG"] and grid[y_water][x_water] != leaf_block_override):
                        grid[y_water][x_water] = water_block_override
                    elif y_water >= surface_y_coords[x_water] and grid[y_water][x_water] == BLOCK_IDS["AIR"]:
                         grid[y_water][x_water] = water_block_override

    min_stone_depth_y = height 
    for x_col in range(width):
        col_stone_start = height
        for y_col in range(height): 
            if grid[y_col][x_col] != BLOCK_IDS["AIR"]:
                col_stone_start = y_col + dirt_thick + 1 
                break
        if surface_y_coords[x_col] + dirt_thick + 1 < col_stone_start : 
             col_stone_start = surface_y_coords[x_col] + dirt_thick + 1

        if col_stone_start < min_stone_depth_y:
            min_stone_depth_y = col_stone_start
    min_stone_depth_y = max(0, min(height -1, min_stone_depth_y))

    # Caves
    if cave_factor > 0:
        cave_spawn_start_y = min_stone_depth_y + int(gen_params.get("cave_depth_offset", 3)) 
        cave_spawn_end_y = height - 5
        cave_size_mult = gen_params.get("cave_size_multiplier", 1.0)
        if cave_spawn_start_y < cave_spawn_end_y:
            for y_cave in range(cave_spawn_start_y, cave_spawn_end_y):
                for x_cave in range(width):
                    if 0 <= y_cave < height and 0 <= x_cave < width and grid[y_cave][x_cave] == main_stone_override:
                        if random.random() < (0.015 * cave_factor): 
                            cx, cy = x_cave, y_cave
                            cave_len = random.randint(int(5 * cave_size_mult), int(15 * cave_size_mult))
                            for _ in range(cave_len):
                                if 0 <= cy < height and 0 <= cx < width and grid[cy][cx] == main_stone_override:
                                    grid[cy][cx] = BLOCK_IDS["AIR"]
                                    if gen_params.get("feature_colored_stones", False) and random.random() < 0.15:
                                        grid[cy][cx] = random.choice([BLOCK_IDS["PURPLE_BLOCK"], BLOCK_IDS["DARK_BLUE_BLOCK"]])

                                    direction = random.choice([(0,1), (0,-1), (1,0), (-1,0)])
                                    forwo, fw = random.choice([-1,0,1]), random.choice([-1,0,1])
                                    if 0 <= cy+forwo < height and 0 <= cx+fw < width and grid[cy+forwo][cx+fw] == main_stone_override:
                                        grid[cy+forwo][cx+fw] = BLOCK_IDS["AIR"]
                                    cx += direction[0]
                                    cy += direction[1]
                                    if not (0 <= cx < width and 0 <= cy < height): break
                                else: break
    # Trees
    if has_trees:
        tree_type = gen_params.get("tree_type", "default") 
        for x_tree in range(width):
            actual_surface_y = -1
            for y_idx in range(height): 
                if 0 <= y_idx < height and grid[y_idx][x_tree] == surface_block_override: 
                    actual_surface_y = y_idx
                    break
            if actual_surface_y != -1:
                if random.random() < gen_params.get("tree_density", 0.08):  
                    tree_height_val = random.randint(gen_params.get("min_tree_height",3), gen_params.get("max_tree_height",6))
                    if actual_surface_y - tree_height_val - 1 < 0: continue
                    for i in range(tree_height_val):
                        trunk_y = actual_surface_y - 1 - i
                        if 0 <= trunk_y < height: grid[trunk_y][x_tree] = BLOCK_IDS["WOOD_LOG"]
                        else: break 
                    trunk_top_actual_y = actual_surface_y - tree_height_val
                    canopy_radius = random.choice([1, 2]) 
                    for ly_offset in range(-canopy_radius, canopy_radius // 2 + 2): 
                        for lx_offset in range(-canopy_radius, canopy_radius + 1):
                            leaf_y, leaf_x = trunk_top_actual_y + ly_offset, x_tree + lx_offset
                            if lx_offset == 0 and ly_offset > canopy_radius // 2 : continue
                            dist_sq = (lx_offset * 0.8)**2 + ly_offset**2 
                            if dist_sq <= (canopy_radius + 0.5)**2 : 
                                if 0 <= leaf_x < width and 0 <= leaf_y < height: 
                                    if grid[leaf_y][leaf_x] == BLOCK_IDS["AIR"]: 
                                        grid[leaf_y][leaf_x] = leaf_block_override
    # Ores & Special Features
    if resource_factor > 0 or gen_params.get("feature_tnt_sprinkle") or gen_params.get("feature_gem_blocks"):
        ore_spawn_start_y = min_stone_depth_y + int(gen_params.get("ore_depth_offset", 5))
        ore_spawn_end_y = height - 3              
        if ore_spawn_start_y < ore_spawn_end_y: 
            for y_ore in range(ore_spawn_start_y, ore_spawn_end_y):
                for x_ore in range(width):
                    if 0 <= y_ore < height and 0 <= x_ore < width and grid[y_ore][x_ore] == main_stone_override:
                        if gen_params.get("feature_tnt_sprinkle", False) and random.random() < gen_params.get("tnt_chance", 0.01):
                            grid[y_ore][x_ore] = BLOCK_IDS["TNT_BLOCK"]
                            continue 
                        
                        if gen_params.get("feature_gem_blocks", False) and random.random() < gen_params.get("gem_block_chance", 0.02):
                            gem_choices = [BLOCK_IDS["PURPLE_BLOCK"], BLOCK_IDS["ORANGE_BLOCK"], BLOCK_IDS["GREEN_BLOCK"], BLOCK_IDS["RED_BLOCK"], BLOCK_IDS["DARK_BLUE_BLOCK"], BLOCK_IDS["LIGHT_BLUE_BLOCK"]]
                            grid[y_ore][x_ore] = random.choice(gem_choices)
                            continue 

                        if resource_factor > 0:
                            r_ore = random.random()
                            if r_ore < (0.003 * resource_factor): grid[y_ore][x_ore] = BLOCK_IDS["DIAMOND"]
                            elif r_ore < (0.006 * resource_factor): grid[y_ore][x_ore] = BLOCK_IDS["RUBY"]
                            elif r_ore < (0.01 * resource_factor): grid[y_ore][x_ore] = BLOCK_IDS["EMERALD"]
                            elif r_ore < (0.018 * resource_factor): grid[y_ore][x_ore] = BLOCK_IDS["GOLD"]
                            elif r_ore < (0.03 * resource_factor): grid[y_ore][x_ore] = BLOCK_IDS["IRON"]
                            elif r_ore < (0.05 * resource_factor): grid[y_ore][x_ore] = BLOCK_IDS["COPPER"]
    return grid

# --- README Generation ---
def generate_readme():
    if not os.path.exists(PLUGIN_DATA_DIR):
        try:
            os.makedirs(PLUGIN_DATA_DIR)
        except OSError as e:
            print(f"[MikuPI Plugin] Error creating directory {PLUGIN_DATA_DIR}: {e}")
            return

    readme_path = os.path.join(PLUGIN_DATA_DIR, "readme.txt")
    try:
        with open(readme_path, "w") as f:
            f.write("MikuPI Plugin - World Generation\n")
            f.write("=================================\n\n")
            f.write("Use command: !genworld [name] [size] [type_id]\n\n")
            f.write("Parameters:\n")
            f.write("  [name]    (Optional) World name. Can be quoted for spaces (e.g., \"My World\").\n")
            f.write("            If omitted, a random name is generated.\n")
            f.write("  [size]    (Optional) World size. Can be:\n")
            f.write("              - small         (100x60)\n")
            f.write("              - medium        (200x100 - default)\n")
            f.write("              - large         (300x150)\n")
            f.write("              - WIDTHxHEIGHT  (e.g., 120x80)\n")
            f.write("              - NUMBER        (e.g., 150 creates a 150x150 world)\n")
            f.write("            If omitted, defaults to 'medium'.\n")
            f.write("  [type_id] (Optional) Integer ID for the world type.\n")
            f.write("            If omitted or invalid, defaults to type 1 (Normal World).\n\n")
            f.write("Examples:\n")
            f.write("  !genworld MyNewAdventure large 3\n")
            f.write("  !genworld \"My Awesome World\" 80x50 7\n")
            f.write("  !genworld AnotherWorld medium\n")
            f.write("  !genworld JustAName\n")
            f.write("  !genworld coolmap 120 2\n\n")
            f.write("Available World Types (use Type ID in command):\n")
            f.write("-----------------------------------------------\n")
            for type_id, type_info in sorted(WORLD_TYPES.items()):
                f.write(f"  ID: {type_id:<3} Name: {type_info['name']:<30} - {type_info['description']}\n")
        print(f"[MikuPI Plugin] Generated/Updated {readme_path}")
    except Exception as e:
        print(f"[MikuPI Plugin] Error generating readme.txt: {e}")


# --- Plugin Hooks ---
async def on_message(websocket, message_str, message_parts, server_api):
    if not message_parts:
        return False

    actual_message_content = ""
    is_player_command = False

    if len(message_parts) >= 4 and message_parts[0] == "PLAYER_MESSAGE" and message_parts[1] == "PLACERCLIENT":
        actual_message_content = message_parts[3].strip()
        is_player_command = True
    
    if is_player_command and actual_message_content.lower() == "!mikupi":
        worlds_dir = "worlds/" 
        worlds_count = 0
        try:
            if os.path.exists(worlds_dir) and os.path.isdir(worlds_dir):
                worlds_count = len([name for name in os.listdir(worlds_dir) if name.endswith(".pw") and os.path.isfile(os.path.join(worlds_dir, name))])
            mikupi_message = f"MIKUPI :) Currently with {worlds_count} worlds."
            await server_api.send_to_client(websocket, f"SERVER_MESSAGE|{mikupi_message}")
        except Exception as e:
            print(f"[MikuPI Plugin] Error counting worlds or sending !mikupi message: {e}")
            await server_api.send_to_client(websocket, "SERVER_MESSAGE|Error getting world count.")
        return True

    if is_player_command and actual_message_content.startswith("!genworld"):
        command_parts_raw = actual_message_content.split()
        
        world_name_str = uuid.uuid4().hex[:8] 
        gen_width, gen_height = DEFAULT_WIDTH, DEFAULT_HEIGHT
        world_type_id = 1 
        
        arg_idx = 1 
        
        if arg_idx < len(command_parts_raw):
            if command_parts_raw[arg_idx].startswith('"'):
                name_buffer = []
                temp_full_message_after_cmd = actual_message_content[len(command_parts_raw[0]):].lstrip()
                
                if temp_full_message_after_cmd.startswith('"'):
                    end_quote_idx = -1
                    try:
                        first_quote = temp_full_message_after_cmd.index('"')
                        search_idx = first_quote + 1
                        while search_idx < len(temp_full_message_after_cmd):
                            found_quote_idx = temp_full_message_after_cmd.find('"', search_idx)
                            if found_quote_idx == -1: 
                                break
                            end_quote_idx = found_quote_idx
                            break
                        
                        if end_quote_idx != -1:
                            world_name_str = temp_full_message_after_cmd[first_quote+1:end_quote_idx]
                            remaining_args_str = temp_full_message_after_cmd[end_quote_idx+1:].strip()
                            command_parts_raw = [command_parts_raw[0]] + [f'"{world_name_str}"'] + remaining_args_str.split()
                            arg_idx = 2 
                        else: 
                            world_name_str = command_parts_raw[arg_idx][1:] 
                            arg_idx +=1
                    except ValueError: 
                         world_name_str = command_parts_raw[arg_idx] 
                         arg_idx += 1
                else: 
                    world_name_str = command_parts_raw[arg_idx]
                    arg_idx += 1

            elif not (command_parts_raw[arg_idx].lower() in ["small", "medium", "large"] or \
                      ('x' in command_parts_raw[arg_idx] and command_parts_raw[arg_idx].replace('x','',1).isdigit()) or \
                      command_parts_raw[arg_idx].isdigit()):
                world_name_str = command_parts_raw[arg_idx]
                arg_idx += 1
        
        if arg_idx < len(command_parts_raw): 
            size_str = command_parts_raw[arg_idx].lower()
            parsed_size = False
            if size_str == "small":
                gen_width, gen_height = 100, 60; parsed_size = True
            elif size_str == "medium":
                gen_width, gen_height = 200, 100; parsed_size = True
            elif size_str == "large":
                gen_width, gen_height = 300, 150; parsed_size = True
            elif 'x' in size_str:
                try:
                    w_str, h_str = size_str.split('x', 1)
                    gen_width, gen_height = int(w_str), int(h_str); parsed_size = True
                except ValueError: pass 
            elif size_str.isdigit(): 
                try:
                    val = int(size_str)
                    gen_width, gen_height = val, val; parsed_size = True
                except ValueError: pass
            if parsed_size:
                arg_idx += 1

        if arg_idx < len(command_parts_raw): 
            try:
                type_id_candidate = int(command_parts_raw[arg_idx])
                if type_id_candidate in WORLD_TYPES:
                    world_type_id = type_id_candidate
            except ValueError:
                pass 

        world_name_str = "".join(c if c.isalnum() or c in ['_', '-',' '] else '' for c in world_name_str).strip()
        if not world_name_str: world_name_str = uuid.uuid4().hex[:8]
        
        gen_width = max(MIN_WIDTH, min(MAX_WIDTH, gen_width))
        gen_height = max(MIN_HEIGHT, min(MAX_HEIGHT, gen_height))

        selected_world_type_info = WORLD_TYPES.get(world_type_id) 
        if not selected_world_type_info:
             await server_api.send_to_client(websocket, f"SERVER_MESSAGE|Error: Invalid world type ID '{world_type_id}'. Defaulting to Normal.")
             selected_world_type_info = WORLD_TYPES[1] 
        
        gen_params = selected_world_type_info["params"]
        world_type_name_display = selected_world_type_info["name"]

        await server_api.send_to_client(websocket, f"SERVER_MESSAGE|Generating '{world_type_name_display}' world: '{world_name_str}' ({gen_width}x{gen_height})... Please wait.")
        
        try:
            loop = asyncio.get_event_loop()
            world_grid = await loop.run_in_executor(None, _generate_world_grid_internal, gen_width, gen_height, gen_params)
            world_data_rle_str = await loop.run_in_executor(None, rle_encode, world_grid, gen_width, gen_height)

            worlds_dir_to_save = "worlds" 
            if not os.path.exists(worlds_dir_to_save):
                os.makedirs(worlds_dir_to_save)
            
            file_name = f"world_{world_name_str.replace(' ', '_')}.pw" 
            file_path = os.path.join(worlds_dir_to_save, file_name)

            world_json_output = {
                "c2tilemap": True,
                "width": gen_width,
                "height": gen_height,
                "data": world_data_rle_str 
            }

            with open(file_path, "w") as f:
                json.dump(world_json_output, f)
            
            success_msg = f"SERVER_MESSAGE|World '{world_name_str}' ({world_type_name_display}) generated and saved as '{file_path}'. (Size: {gen_width}x{gen_height})"
            await server_api.send_to_client(websocket, success_msg)
            print(f"[MikuPI Plugin] {success_msg}")

        except Exception as e:
            error_msg = f"SERVER_MESSAGE|Error during world generation: {e}"
            await server_api.send_to_client(websocket, error_msg)
            print(f"[MikuPI Plugin] Error during world generation: {e}")
            traceback.print_exc()
        return True 

    return False


def on_load(server_api_instance):
    print("[MikuPI Plugin] MikuPI World Gen & Info Plugin Loaded.")
    generate_readme() 
    print(f"[MikuPI Plugin] Use !genworld [name] [size] [type_id] to generate a new world. See {os.path.join(PLUGIN_DATA_DIR, 'readme.txt')} for types.")
    print("[MikuPI Plugin] Use !mikupi to see world count.")
    server_api_instance.log(f"MikuPI Plugin ready. Commands: !genworld, !mikupi. Readme: {os.path.join(PLUGIN_DATA_DIR, 'readme.txt')}")

