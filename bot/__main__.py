import logging
import os
import requests
import subprocess
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
import asyncio

# Load environment variables from .env file
load_dotenv()

# Initialize logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load bot token, owner ID, API Key, and Hash Key from environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = 6472109162
API_KEY = os.getenv("API_KEY")  # New API Key
HASH_KEY = os.getenv("HASH_KEY")  # New Hash Key

# Torrent download directory from environment variable
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/path/to/download")

# Ensure download directory exists
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Dictionary to track ongoing downloads
user_downloads = {}

# Function to check if the user is the owner
def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

# Function to start the bot
@Client.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("Hello! Send me a torrent magnet link or a direct download link, and I will handle it.")

# Handle text messages (magnet or download link)
@Client.on_message(filters.text & ~filters.command("mirror"))
async def handle_torrent_or_link(client, message):
    user_id = message.from_user.id
    input_link = message.text

    if "magnet:" in input_link:
        await handle_magnet_link(client, message, input_link)
    elif input_link.startswith("http://") or input_link.startswith("https://"):
        await handle_direct_link(client, message, input_link)
    else:
        await message.reply_text("Please send a valid magnet link or a direct download link.")

# Handle torrent magnet links
async def handle_magnet_link(client, message, magnet_link):
    user_id = message.from_user.id
    download_path = os.path.join(DOWNLOAD_DIR, f"{user_id}_torrent")

    try:
        # Log API_KEY and HASH_KEY usage if necessary (can be used for an external service)
        logger.info(f"Using API_KEY: {API_KEY}, HASH_KEY: {HASH_KEY}")

        # Command to download the torrent (aria2c is assumed to be installed)
        command = ['aria2c', '--dir', DOWNLOAD_DIR, magnet_link]
        logger.info(f"Starting torrent download: {command}")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Track the download with the message ID
        user_downloads[user_id] = {'process': process, 'message_id': message.message_id, 'download_path': download_path}
        await message.reply_text(f"Downloading torrent: {magnet_link}")

        # Track download progress and update the user
        while process.poll() is None:
            await asyncio.sleep(5)  # Delay to avoid spamming
            await message.reply_text(f"Downloading {magnet_link}...")

        if process.returncode == 0:
            await message.reply_text(f"Torrent download complete. File saved to {download_path}.")
        else:
            await message.reply_text(f"Error downloading torrent. Please try again later.")
    except Exception as e:
        logger.error(f"Error handling magnet link: {e}")
        await message.reply_text("There was an error processing your torrent link.")
        del user_downloads[user_id]

# Handle direct download links
async def handle_direct_link(client, message, download_link):
    user_id = message.from_user.id
    try:
        file_name = download_link.split("/")[-1]
        download_path = os.path.join(DOWNLOAD_DIR, file_name)

        await message.reply_text(f"Downloading file: {file_name}...")

        # Use requests to handle the file download
        with requests.get(download_link, stream=True) as r:
            r.raise_for_status()  # Raise error for bad status codes
            with open(download_path, 'wb') as f:
                total_size = int(r.headers.get('Content-Length', 0))
                chunk_size = 8192
                downloaded_size = 0

                # Track progress and download the file in chunks
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        # Update the user on progress
                        progress = (downloaded_size / total_size) * 100 if total_size else 0
                        await message.reply_text(f"Downloading {file_name}: {progress:.2f}% complete.")

        await message.reply_text(f"Download of {file_name} completed! Choose a file type to upload.",
                                 reply_markup=build_file_type_keyboard(download_path))
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading file: {e}")
        await message.reply_text("Error while downloading the file. Please try again.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await message.reply_text("An unexpected error occurred while downloading the file.")

# Build the inline keyboard with file type options
def build_file_type_keyboard(file_path: str):
    file_types = ['.mp4', '.zip', '.pdf', '.jpg', '.png']
    keyboard = []
    for file_type in file_types:
        keyboard.append([InlineKeyboardButton(f"Send {file_type} file", callback_data=f"send_{file_type}")])

    return InlineKeyboardMarkup(keyboard)

# Handle file type selection and upload
@Client.on_callback_query(filters.regex('^send_'))
async def handle_file_type_selection(client, query):
    user_id = query.from_user.id
    if user_id not in user_downloads:
        await query.edit_message_text("No download in progress or completed.")
        return

    selected_file_type = query.data.split('_')[1]
    file_path = os.path.join(DOWNLOAD_DIR, user_downloads[user_id]['download_path'])
    
    selected_file = get_file_of_type(file_path, selected_file_type)

    if selected_file:
        await query.edit_message_text(f"Uploading your {selected_file_type} file...")
        await upload_file_with_progress(client, query, selected_file)
    else:
        await query.edit_message_text(f"No {selected_file_type} file found in the downloaded torrent.")

# Helper function to get a file of the specified type
def get_file_of_type(file_path: str, file_type: str):
    for root, dirs, files in os.walk(file_path):
        for file in files:
            if file.lower().endswith(file_type):
                return os.path.join(root, file)
    return None

# Upload file with progress tracking
async def upload_file_with_progress(client, query, file_path):
    try:
        await client.send_document(query.from_user.id, document=file_path)
        await query.edit_message_text(f"Upload completed for {file_path}!")
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        await query.edit_message_text(f"Error uploading file: {file_path}. Please try again.")

# Detect if a message related to a download has been deleted
@Client.on_deleted_messages()
async def on_message_deleted(client, deleted_messages):
    for msg in deleted_messages:
        user_id = msg.from_user.id

        # Check if the deleted message is related to an ongoing download
        if user_id in user_downloads and user_downloads[user_id]['message_id'] == msg.message_id:
            # Stop the ongoing download (if applicable)
            process = user_downloads[user_id]['process']
            if process.poll() is None:
                process.terminate()  # Terminate the process
                logger.info(f"Download process terminated due to message deletion by user {user_id}.")
            
            del user_downloads[user_id]  # Clean up the user’s download data
            await client.send_message(user_id, "Your download was canceled because you deleted the message.")

# Create and run the client
app = Client("torrent_bot", bot_token=TOKEN)

if __name__ == '__main__':
    app.run()
