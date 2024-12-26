import logging
import os
import requests
import subprocess
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Initialize logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Telegram Bot Token
TOKEN = '7505846620:AAFvv-sFybGfFILS-dRC8l7ph_0rqIhDgRM'  # Replace with your actual Telegram bot token

# Torrent download directory
DOWNLOAD_DIR = '/path/to/download'

# Bot Owner ID (replace with your actual Telegram user ID)
OWNER_ID = 6472109162  # Replace with your own Telegram user ID

# Dictionary to track ongoing downloads
user_downloads = {}

# Function to check if the user is the owner
def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

# Function to start the bot
@Client.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("Hello! Send me a torrent magnet link or a direct download link, and I will handle it.")

# Function to handle either torrent magnet links or direct download links
@Client.on_message(filters.text & ~filters.command())
async def handle_torrent_or_link(client, message):
    user_id = message.from_user.id
    input_link = message.text

    if "magnet:" in input_link:
        # Handle as a magnet link
        await handle_magnet_link(client, message, input_link)
    elif input_link.startswith("http://") or input_link.startswith("https://"):
        # Handle as a direct download link
        await handle_direct_link(client, message, input_link)
    else:
        await message.reply_text("Please send a valid magnet link or a direct download link.")

# Function to handle torrent magnet links with aria2
async def handle_magnet_link(client, message, magnet_link):
    user_id = message.from_user.id
    download_path = os.path.join(DOWNLOAD_DIR, f"{user_id}_torrent")

    try:
        # Start aria2c to download the torrent
        command = ['aria2c', '--dir', DOWNLOAD_DIR, magnet_link]
        logger.info(f"Starting torrent download: {command}")

        # Run the aria2c command
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Track the download
        user_downloads[user_id] = {'process': process, 'message_id': message.message_id, 'download_path': download_path}
        await message.reply_text(f"Downloading torrent: {magnet_link}")

        # Monitor the aria2c process
        while process.poll() is None:
            # Periodically check for progress and notify the user
            # You can improve this to show progress or specific download stats
            await message.reply_text(f"Downloading {magnet_link}...")

        # Check if the download is complete
        if process.returncode == 0:
            await message.reply_text(f"Torrent download complete. File saved to {download_path}.")
        else:
            await message.reply_text(f"Error downloading torrent.")

    except Exception as e:
        logger.error(f"Error handling magnet link: {e}")
        await message.reply_text("There was an error processing your torrent link.")
        del user_downloads[user_id]  # Remove from tracking in case of error

# Function to handle direct download links
async def handle_direct_link(client, message, download_link):
    user_id = message.from_user.id

    try:
        # Extract the file name from the URL
        file_name = download_link.split("/")[-1]
        download_path = os.path.join(DOWNLOAD_DIR, file_name)

        # Download the file
        await message.reply_text(f"Downloading file: {file_name}...")

        # Stream the content and save it to the download directory
        with requests.get(download_link, stream=True) as r:
            if r.status_code == 200:
                with open(download_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

                await message.reply_text(f"Download of {file_name} completed! Choose a file type to upload.",
                                         reply_markup=build_file_type_keyboard(download_path))
            else:
                await message.reply_text("Failed to download the file. Please check the link and try again.")
    except Exception as e:
        logger.error(f"Error downloading direct link: {e}")
        await message.reply_text("There was an error processing your direct download link.")

# Build the inline keyboard with file type options
def build_file_type_keyboard(file_path: str):
    file_types = ['.mp4', '.zip', '.pdf', '.jpg', '.png']  # Define file types
    keyboard = []

    for file_type in file_types:
        keyboard.append([InlineKeyboardButton(f"Send {file_type} file", callback_data=f"send_{file_type}")])

    return InlineKeyboardMarkup(keyboard)

# Handle the button press and upload the selected file type
@Client.on_callback_query(filters.regex('^send_'))
async def handle_file_type_selection(client, query):
    selected_file_type = query.data.split('_')[1]
    user_id = query.from_user.id
    file_path = os.path.join(DOWNLOAD_DIR, user_downloads[user_id]['download_path'])

    # Check if the file has already been uploaded
    if file_path in user_downloads:
        await query.edit_message_text(text=f"The file has already been uploaded to Telegram.")
    else:
        selected_file = get_file_of_type(file_path, selected_file_type)

        if selected_file:
            await query.edit_message_text(text=f"Uploading your {selected_file_type} file...")
            await upload_file_with_progress(client, query, selected_file)
        else:
            await query.edit_message_text(text=f"No {selected_file_type} file found in the downloaded torrent.")

# Helper function to get a file of the specified type
def get_file_of_type(file_path: str, file_type: str):
    for root, dirs, files in os.walk(file_path):
        for file in files:
            if file.lower().endswith(file_type):
                return os.path.join(root, file)
    return None

# Upload file with progress tracking (fixed upload)
async def upload_file_with_progress(client, query, file_path):
    total_size = os.path.getsize(file_path)  # Get the total size of the file
    await client.send_document(query.from_user.id, document=file_path)

    await query.edit_message_text(text=f"Upload completed for {file_path}!")

# Create and run the client
app = Client("torrent_bot", bot_token=TOKEN)

if __name__ == '__main__':
    app.run()
