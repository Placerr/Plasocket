import asyncio
import os
import base64
from io import BytesIO
from PIL import Image, ImageSequence
import traceback

# --- Plugin Configuration ---
# Establishes the folder structure for the plugin.
PLUGIN_FOLDER = "plugins/GifPlayer"
MEDIA_FOLDER = os.path.join(PLUGIN_FOLDER, "media")

# --- Global State ---
# A lock to prevent multiple GIFs or images from playing at the same time.
# This avoids visual chaos and potential network spam.
playback_lock = asyncio.Lock()

# --- Main Plugin Logic ---

async def play_gif_to_all(gif_path, server_api, loop_count=1):
    """
    Extracts frames from a GIF, encodes them, and broadcasts them to all players.
    Can loop the GIF a specified number of times.
    """
    if playback_lock.locked():
        server_api.log("ImagePlayer: Ignoring request, another image/GIF is already in progress.")
        return

    async with playback_lock:
        try:
            server_api.log(f"ImagePlayer: Starting GIF playback of {os.path.basename(gif_path)}, looping {loop_count} time(s).")
            
            with Image.open(gif_path) as img:
                # Loop for the user-specified number of times.
                for i in range(loop_count):
                    # For each loop, we must go back to the first frame of the GIF.
                    img.seek(0)
                    
                    # Iterate through each frame of the animated GIF.
                    for frame in ImageSequence.Iterator(img):
                        frame_duration_ms = frame.info.get('duration', 100)
                        
                        if frame_duration_ms < 10:
                            frame_duration_ms = 100

                        frame_duration_sec = frame_duration_ms / 1000.0
                        frame_rgba = frame.convert('RGBA')
                        
                        buffer = BytesIO()
                        frame_rgba.save(buffer, format="PNG")
                        buffer.seek(0)
                        
                        base64_data = base64.b64encode(buffer.read()).decode('utf-8')
                        full_data_url = f"data:image/png;base64,{base64_data}"
                        message = f"SHOW_IMAGE|PLACERSERVER|{full_data_url}"
                        
                        await server_api.broadcast(message)
                        await asyncio.sleep(frame_duration_sec)

        except FileNotFoundError:
            server_api.log(f"ImagePlayer: ERROR - GIF file not found at {gif_path}")
        except Exception as e:
            server_api.log(f"ImagePlayer: An error occurred during GIF playback: {e}")
            traceback.print_exc()
        finally:
            server_api.log("ImagePlayer: GIF playback finished. Hiding image.")
            await server_api.broadcast("HIDE_IMAGE|PLACERSERVER|")

async def show_static_image_to_all(image_path, server_api, duration_sec=10):
    """
    Opens a static image, converts it to a base64 PNG, and shows it to all players for a set duration.
    """
    if playback_lock.locked():
        server_api.log("ImagePlayer: Ignoring request, another image/GIF is already in progress.")
        return

    async with playback_lock:
        try:
            server_api.log(f"ImagePlayer: Displaying static image {os.path.basename(image_path)}")
            
            with Image.open(image_path) as img:
                img_rgba = img.convert('RGBA')
                buffer = BytesIO()
                img_rgba.save(buffer, format="PNG")
                buffer.seek(0)
                
                base64_data = base64.b64encode(buffer.read()).decode('utf-8')
                full_data_url = f"data:image/png;base64,{base64_data}"
                message = f"SHOW_IMAGE|PLACERSERVER|{full_data_url}"
                
                await server_api.broadcast(message)
                await asyncio.sleep(duration_sec)

        except FileNotFoundError:
            server_api.log(f"ImagePlayer: ERROR - Image file not found at {image_path}")
        except Exception as e:
            server_api.log(f"ImagePlayer: An error occurred during image display: {e}")
            traceback.print_exc()
        finally:
            server_api.log("ImagePlayer: Hiding static image.")
            await server_api.broadcast("HIDE_IMAGE|PLACERSERVER|")


# --- Plugin Hooks ---

def on_load(server_api):
    server_api.log("ImagePlayer Plugin: Loading...")
    if not os.path.exists(PLUGIN_FOLDER): os.makedirs(PLUGIN_FOLDER)
    if not os.path.exists(MEDIA_FOLDER): os.makedirs(MEDIA_FOLDER)
    server_api.log("ImagePlayer Plugin: Loaded successfully!")

def on_unload(server_api):
    server_api.log("ImagePlayer Plugin: Unloaded.")

async def on_connect(websocket, server_api):
    pass

async def on_message(websocket, message_string, message_parts, server_api):
    if len(message_parts) >= 4 and message_parts[0] == "PLAYER_MESSAGE" and message_parts[1] == "PLACERCLIENT":
        command_line = message_parts[3].strip().split()
        if not command_line: return False
        
        command = command_line[0]
        username = message_parts[2]
        
        # --- GIF Command Handler ---
        if command == "!playgif" and len(command_line) > 1:
            gif_name = command_line[1]
            if ".." in gif_name or "/" in gif_name or "\\" in gif_name: return False

            # --- New Loop Logic ---
            loop_count = 1  # Default to playing once
            if len(command_line) > 2 and command_line[2].lower().startswith("loop"):
                try:
                    num_str = command_line[2][4:]
                    if num_str.isdigit():
                        loop_count = int(num_str)
                        # Add a sane limit to prevent abuse (e.g., !playgif cat loop9999)
                        if loop_count > 20: loop_count = 20
                        if loop_count < 1: loop_count = 1
                except (ValueError, IndexError):
                    pass # If parsing fails, just stick with the default of 1

            gif_path = os.path.join(MEDIA_FOLDER, f"{gif_name}.gif")
            
            if os.path.exists(gif_path):
                server_api.log(f"ImagePlayer: {username} initiated playback of {gif_name}.gif")
                asyncio.create_task(play_gif_to_all(gif_path, server_api, loop_count=loop_count))
            else:
                msg = f"TELLRAW|PLACERSERVER|GIF not found: {gif_name}.gif"
                await server_api.send_to_client(websocket, msg)
            return True

        # --- Static Image Command Handler ---
        elif command == "!playimg" and len(command_line) > 1:
            img_name = command_line[1]
            if ".." in img_name or "/" in img_name or "\\" in img_name: return False

            supported_extensions = ['.png', '.jpg', '.jpeg', '.webp', '.bmp']
            img_path = None
            for ext in supported_extensions:
                potential_path = os.path.join(MEDIA_FOLDER, f"{img_name}{ext}")
                if os.path.exists(potential_path):
                    img_path = potential_path
                    break
            
            if img_path:
                server_api.log(f"ImagePlayer: {username} initiated display of {os.path.basename(img_path)}")
                asyncio.create_task(show_static_image_to_all(img_path, server_api))
            else:
                msg = f"TELLRAW|PLACERSERVER|Image not found. Looked for: {img_name} with extensions {supported_extensions}"
                await server_api.send_to_client(websocket, msg)
            return True
            
    return False

async def on_disconnect(websocket, server_api):
    pass
