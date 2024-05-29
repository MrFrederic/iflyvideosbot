from dotmap import DotMap
import asyncio
import logging
import os
import io
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaDocument
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from dotenv import load_dotenv


# Load environment variables
load_dotenv('.env')
BOT_TOKEN = os.getenv("BOT_TOKEN")
SYSTEM_DATA_FILE = os.getenv("SYSTEM_DATA_FILE")
IFLY_CHAT_ID = int(os.getenv("IFLY_CHAT_ID"))


# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


# Storage functions
async def get_storage_message(update: Update, context: CallbackContext, chat_id=None):
    """
    Retrieve the pinned message in the chat to use as storage. If none exists, create a new one.
    """
    if not chat_id:
        chat_id = update.message.chat_id
        
    
    try:
        chat = await context.bot.get_chat(chat_id)
        add_or_update_user(update, chat_id, chat.username)
        if chat.pinned_message:
            pinned_message = chat.pinned_message
            logger.info("Pinned message found")
        else:
            logger.info("No pinned message in this chat. Creating new storage message")
            pinned_message = await create_storage_message(update, context, chat_id)
        return pinned_message
    except Exception as e:
        logger.error(f"Error retrieving storage message: {e}")
        return None

async def load_local_data(update: Update, context: CallbackContext, chat_id=None):
    """
    Load the JSON storage from the pinned message document.
    """
    if not chat_id:
        chat_id = update.message.chat_id
    try:
        message = await get_storage_message(update, context, chat_id)
        if not message or not message.document:
            logger.error("Pinned message doesn't contain document")
            return None

        file_info = await context.bot.get_file(message.document.file_id)
        byte_array = await file_info.download_as_bytearray()
        data = byte_array.decode('utf-8')
        return json.loads(data)
    except Exception as e:
        logger.error(f"Error while loading storage: {e}")
        return None

async def save_local_data(update: Update, context: CallbackContext, local_data, chat_id=None):
    """
    Save the video storage JSON data to the pinned message document.
    """
    if not chat_id:
        chat_id = update.message.chat_id
    try:
        file_buffer = io.BytesIO()
        file_buffer.write(json.dumps(local_data).encode('utf-8'))
        file_buffer.seek(0)
        message = await get_storage_message(update, context, chat_id)
        if not message:
            logger.error("No storage message available to save data")
            return None
        await message.edit_media(
            media=InputMediaDocument(
                media=file_buffer,
                filename="data.json",
                caption="This is a service message. Please, do not delete or unpin it!"
            )
        )
        logger.info("Storage message updated.")
        return message
    except Exception as e:
        logger.error(f"Error updating storage message: {e}")
        return None


# Service Functions
def parse_filename(filename):
    """
    Parse the filename to extract camera name, flight number, and date.
    """
    try:
        filename = filename.replace('-', '_')
        parts = filename.split('_')
        date_str = '_'.join(parts[4:7])
        date = datetime.strptime(date_str, '%Y_%m_%d').strftime('%Y_%m_%d')
        flight_number = parts[3]
        camera_name = parts[2]
        return {
            'date': date,
            'flight_number': flight_number,
            'camera_name': camera_name
        }
    except Exception as e:
        logger.error(f"Error parsing filename: {e}")
        raise

def generate_unique_id(storage, key="session_id"):
    """
    Generate a unique ID for sessions or videos in the storage.
    """
    try:
        current_ids = [item[key] for item in storage]
        return max(current_ids, default=0) + 1
    except Exception as e:
        logger.error(f"Error generating unique ID: {e}")
        raise

def get_or_create_session(local_data, date):
    """
    Retrieve or create a new session based on the provided date.
    """
    try:
        for session in local_data["sessions"]:
            if session["date"] == date:
                return session
        
        new_session = {
            "session_id": generate_unique_id(local_data["sessions"]),
            "date": date,
            "flights": []
        }
        local_data["sessions"].append(new_session)
        local_data["sessions"].sort(key=lambda s: datetime.strptime(s["date"], '%Y_%m_%d'))
        for idx, session in enumerate(local_data["sessions"]):
            session["session_id"] = idx + 1
        return new_session
    except Exception as e:
        logger.error(f"Error getting or creating session: {e}")
        raise

def get_or_create_flight(session, flight_number, length=None):
    """
    Retrieve or create a new flight based on the provided flight number.
    """
    try:
        for flight in session["flights"]:
            if flight["flight_id"] == flight_number:
                return flight
        
        new_flight = {
            "flight_id": flight_number,
            "videos": [],
            "length": length
        }
        session["flights"].append(new_flight)
        return new_flight
    except Exception as e:
        logger.error(f"Error getting or creating flight: {e}")
        raise

def menu_message_text(local_data, current_session=None, current_flight=None):
    """
    Generate the menu message text for the current video storage state.
    """
    try:
        message = []
        
        sessions = local_data.get("sessions", [])
        
        session = next((s for s in sessions if s["session_id"] == current_session), None)
        flights = session.get("flights", []) if session else []
        
        flight = next((f for f in flights if f["flight_id"] == current_flight), None)
        videos = flight.get("videos", []) if flight else []
        for s in sessions:
            if s == session:
                message.append(f"\- *Session {s['session_id']}: {s['date'].replace('_','\.')}*")
            else:
                message.append(f"\- Session {s['session_id']}: {s['date'].replace('_','\.')}")
            if s == session:
                for f in flights:
                    if f == flight:
                        message.append(f"\- \- *Flight {f['flight_id']}: {f['length']//60}:{f['length']%60} min*")
                    else:
                        message.append(f"\- \- Flight {f['flight_id']}: {f['length']//60}:{f['length']%60} min")
                    if f == flight:
                        for v in videos:
                            message.append(f"\- \- \- {v['camera_name']}")
        return "\n".join(message)
    except Exception as e:
        logger.error(f"Error generating menu message text: {e}")
        raise

async def find_video(update: Update, context: CallbackContext, session_id, flight_id, video_id):
    """
    Find a specific video in the storage based on session, flight, and video IDs.
    """
    try:
        local_data = await load_local_data(update, context)
        session = next((s for s in local_data.get("sessions", []) if s["session_id"] == session_id), None)
        if not session:
            return None, None, None
        flight = next((f for f in session["flights"] if f["flight_id"] == flight_id), None)
        if not flight:
            return session, None, None
        video = next((v for v in flight.get("videos", []) if v["video_id"] == video_id), None)
        return session, flight, video
    except Exception as e:
        logger.error(f"Error finding video: {e}")
        return None, None, None

def total_flight_time(local_data):
    """
    Calculate the total flight time across all sessions.
    """
    total_time = 0
    for session in local_data["sessions"]:
        for flight in session["flights"]:
            total_time += flight["length"]
    return total_time

def days_since_first_session(local_data):
    """
    Calculate the number of days since the first session.
    """
    if not local_data["sessions"]:
        return 0

    # Find the earliest date in the sessions
    earliest_date_str = min(session["date"] for session in local_data["sessions"])
    earliest_date = datetime.strptime(earliest_date_str, "%Y_%m_%d")
    
    # Calculate the number of days since the earliest session
    current_date = datetime.now()
    days_since_first = (current_date - earliest_date).days
    
    return days_since_first

def save_system_data(data=None):
    if not data:
        data = {
            "ifly_chat": {
                "state": "username",
                "session": {
                    "username": "MrFrederic",
                    "chat_id": 932162499,
                    "ends": 123456
                },
                "menu_message_id": 0
            },
            "users": [{
                "username": "MrFrederic",
                "chat_id": 932162499
            }]
        }
        data = DotMap(data)
        
    # Convert the JSON data to a string
    json_data = json.dumps(data, indent=4)
    
    # Save the JSON data to a file
    with open(SYSTEM_DATA_FILE, 'w') as json_file:
        json_file.write(json_data)
        
def load_system_data():
    with open(SYSTEM_DATA_FILE, 'r') as f:
        return DotMap(json.load(f))

def check_ifly_chat_state(state):
    try:
        data = load_system_data()
        return data.ifly_chat.session.status == state
    except Exception as e:
        logger.error(f"Error check_ifly_chat_state: {e}")
        raise

def update_ifly_chat_state(state):
    try:
        data = load_system_data()
        data.ifly_chat.session.status = state
        save_system_data(data)
    except Exception as e:
        logger.error(f"Error update_ifly_chat_state: {e}")
        raise
    
async def ifly_menu_message_id(context: CallbackContext):
    try: 
        data = load_system_data()
        message_id  = data.ifly_chat.menu_message_id
        if not message_id:
            message = await context.bot.send_message(chat_id=IFLY_CHAT_ID, text="Loading")
            data.ifly_chat.menu_message_id = message.message_id
        else:
            try:
                await context.bot.edit_message_text("Loading", IFLY_CHAT_ID, message_id)
            except Exception:
                message = await context.bot.send_message(chat_id=IFLY_CHAT_ID, text="Loading")
                data.ifly_chat.menu_message_id = message.message_id

        save_system_data(data)
        return data.ifly_chat.menu_message_id
    except Exception as e:
        logger.error(f"Error ifly_menu_message_id: {e}")
        raise
    
def add_or_update_user(update: Update, chat_id=None, username=None):
    try:
        data = load_system_data()
        if not chat_id:
            chat_id = update.message.chat_id
        if not username:
            username = update.message.from_user.username
        i = 0
        for user in data.users:
            if user.chat_id == chat_id:
                logger.info("User found, updating")
                user.username = username
                save_system_data(data)
                return
        logger.info("User Not found, creating")
        new_user = {"username": username, "chat_id": chat_id}
        data.users.append(new_user)
        save_system_data(data)
    except Exception as e:
        logger.error(f"Error add_or_update_user: {e}")
        raise

async def delete_message(update: Update,context: CallbackContext, chat_id, message_id):
    await context.bot.delete_message(chat_id, message_id)

# Command handlers
async def create_storage_message(update: Update, context: CallbackContext, chat_id=None):
    """
    Create a new storage message and pin it in the chat.
    """
    if not chat_id:
        chat_id = update.message.chat_id
    try:
        local_data = {"sessions": []}
        file_buffer = io.BytesIO()
        file_buffer.write(json.dumps(local_data).encode('utf-8'))
        file_buffer.seek(0)
        message = await context.bot.send_document(
            chat_id=chat_id,
            document=file_buffer,
            filename="data.json",
            caption="This is a service message. Please, do NOT delete, unpin or pin amy onther messages in this chat! This may result in losing all your data."
        )
        await message.pin(disable_notification=True)
        logger.info("Storage message created and pinned")
        return message
    except Exception as e:
        logger.error(f"Error creating storage message: {e}")
        return None

async def clear_local_data(update: Update, context: CallbackContext):
    """
    Clear the storage by resetting it to an empty state.
    """
    try:
        local_data = {"sessions": []}
        await save_local_data(update, context, local_data)
        await update.message.reply_text("All stored videos have been cleared.")
    except Exception as e:
        logger.error(f"Error clearing storage: {e}")

async def show_local_data(update: Update, context: CallbackContext):
    """
    Display the contents of the storage.
    """
    try:
        local_data = await load_local_data(update, context)
        logger.info("Video storage contents:")
        logger.info(json.dumps(local_data, indent=4))
    except Exception as e:
        logger.error(f"Error showing storage: {e}")

async def start(update: Update, context: CallbackContext, edit=0):
    try:
        await update.message.delete()
        if update.message.chat_id == IFLY_CHAT_ID:
            await ask_for_username(update, context)
        else:
            add_or_update_user(update)
            await show_start_menu(update, context)
    except Exception as e:
        logger.error(f"Error start command: {e}")
        
async def help(update: Update, context: CallbackContext):
    try:
        await update.message.delete()
        if update.message.chat_id == IFLY_CHAT_ID:
            text = """You can send your videos to your bot after completing authentification"""
        else:
            text = """Awailable commands\:\n\/start \- Shows menu\n\/help \- Shows this message\n\/info \- Shows info message\n\/clear\_data \- Carefull\!\!\! Delets all saved videos\!\n\nTo upload videos \- just drop them here\. Bot will automatically find their correct flight\. Alternetively, you can send them from \@iFLYvideo account after completing authentification\."""

        message = await update.message.reply_text(text, parse_mode='MarkdownV2')
        message_id = message.message_id
        chat_id = update.message.chat_id
        keyboard = [
            [
                InlineKeyboardButton("Close", callback_data=f"delete:{chat_id}:{message_id}"),
            ]
        ] 
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.edit_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error help command: {e}")


# JSON file handling (aka updating video storage)
async def edit_local_data(update: Update, context: CallbackContext):
    """
    Edit the storage by updating it with a new JSON file.
    """
    try:
        message = update.message
        if not message.document:
            logger.error("Message doesn't contain document")
            return None

        file_info = await context.bot.get_file(message.document.file_id)
        byte_array = await file_info.download_as_bytearray()
        data = byte_array.decode('utf-8')
        local_data = json.loads(data)
        await save_local_data(update, context, local_data)
        logger.info("Storage updated manually")
        await message.delete()
    except Exception as e:
        logger.error(f"Error editing storage: {e}")


# Video handling (aka uploading video)
async def upload_video(update: Update, context: CallbackContext):
    """
    Handle video uploads by extracting metadata and storing it.
    """
    try:
        if not update.message.chat_id == IFLY_CHAT_ID:
            add_or_update_user(update)
            chat_id = update.message.chat_id
        else:
            data = load_system_data()
            if data.ifly_chat.session.ends < int(datetime.now().timestamp()):
                text = "To upload videos - please send your username\n\nSorry, your session expired"
                await context.bot.edit_message_text(text, IFLY_CHAT_ID, await ifly_menu_message_id(context))
                update_ifly_chat_state("no")
                return
            chat_id = data.ifly_chat.session.chat_id
        local_data = await load_local_data(update, context, chat_id)
        video = update.message.video
        file_id = video.file_id
        file_name = video.file_name
        file_duration = round(video.duration / 5) * 5

        video_info = parse_filename(file_name)
        date = video_info['date']
        flight_number = int(video_info['flight_number'])
        camera_name = video_info['camera_name']
        logger.info(f"Received video: file_id={file_id}, file_name={file_name}, duration={file_duration}s")

        session = get_or_create_session(local_data, date)
        flight = get_or_create_flight(session, flight_number, file_duration)

        # Check for duplicate video across all flights in all sessions
        duplicate_found = any(
            video["filename"] == file_name
            for session in local_data["sessions"]
            for flight in session["flights"]
            for video in flight["videos"]
        )

        if not duplicate_found:
            video_id = generate_unique_id(flight["videos"], key="video_id")
            flight["videos"].append({
                "video_id": video_id,
                "filename": file_name,
                "camera_name": camera_name,
                "file_id": file_id
            })
            await save_local_data(update, context, local_data, chat_id)
            logger.info(f"Video {file_name} added successfully.")
        else:
            logger.info(f"Ignoring duplicate video with filename: {file_name}")
        
        await update.message.delete()
        logger.info("Deleted the original video message.")
    except ValueError as e:
        await update.message.reply_text(str(e))
        logger.error(f"Value error in upload_video: {e}")
    except Exception as e:
        logger.error(f"Error uploading video: {e}")


# Inline button handling
async def inline_button(update: Update, context: CallbackContext):
    """
    Handle inline button presses and route to the appropriate function.
    """
    try:
        query = update.callback_query
        
        await query.answer()
        
        if query.message.chat_id == IFLY_CHAT_ID:
            await ifly_inline_buttons(update, context, query)
        else: 
            parts = query.data.split(':')
            handler = {
                "start": show_start_menu,
                "stats": show_statistics,
                "home": show_sessions,
                "session": show_flights,
                "flight": show_videos,
                "video": open_video,
                "auth": start_session,
                "delete": delete_message
            }.get(parts[0])
            if handler:
                await handler(query, context, *map(int, parts[1:]))
    except Exception as e:
        logger.error(f"Error handling callback data: {e}")
        # await query.message.reply_text(f"An error occurred while processing button: {e}")


# Menu display functions
async def show_start_menu(update: Update, context: CallbackContext, edit=0):
    """
    Start menu
    """
    try:
        text = "Welcome to the Bodyflight Video Bot\! Use buttons to navigate\."
        keyboard = [
            [
                InlineKeyboardButton("Browse Videos", callback_data="home:1"),
                InlineKeyboardButton("My Stats", callback_data="stats"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if edit == 1:
            await update.message.edit_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error sending start message: {e}")

async def show_statistics(update: Update, context: CallbackContext):
    """
    Stats
    """
    
    def format_flight_time(seconds):
            hours, remainder = divmod(seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            if hours > 0:
                return f"{hours} hour \: {minutes} min \: {seconds} sec"
            elif minutes > 0:
                return f"{minutes} min \: {seconds} sec"
            else:
                return f"{seconds} sec"
            
    def format_days_count(days):
        years, remainder = divmod(days, 365)
        months, days = divmod(remainder, 30)
        
        if years > 0:
            return f"{years} year\(s\) \: {months} month\(s\) \: {days} day\(s\)"
        elif months > 0:
            return f"{months} month\(s\) \: {days} day\(s\)"
        else:
            return f"{days} day\(s\)"
        
    try:
        local_data = await load_local_data(update, context)
        flight_time = "You have flown for " + format_flight_time(total_flight_time(local_data))
        days_flown = "You started flying " + format_days_count(days_since_first_session(local_data)) + " ago"
        text = "\n".join([
            "Here is some entertaining stats\:", 
            days_flown,
            flight_time
        ])
        
        keyboard = [
            [
                InlineKeyboardButton("<- Back", callback_data="start:1")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.edit_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error sending start message: {e}")

async def show_sessions(update: Update, context: CallbackContext, edit=0):
    """
    Show the list of sessions in the storage.
    """
    try:
        add_or_update_user(update)
        local_data = await load_local_data(update, context)
        sessions = local_data.get("sessions", [])
        if not sessions:
            text = "No sessions found"
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("<- Home", callback_data="start:1")]])
        else:
            text = menu_message_text(local_data)
            session_buttons = [InlineKeyboardButton(f"Session {session['session_id']}", callback_data=f"session:{session['session_id']}") for session in sessions]
            reply_markup = InlineKeyboardMarkup([[button] for button in session_buttons] + [[InlineKeyboardButton("<- Home", callback_data="start:1")]])
        if edit == 1:
            await update.message.edit_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error showing sessions: {e}")

async def show_flights(update: Update, context: CallbackContext, session_id):
    """
    Show the list of flights for a specific session.
    """
    try:
        local_data = await load_local_data(update, context)
        session = next((s for s in local_data.get("sessions", []) if s["session_id"] == session_id), None)
        if not session:
            await update.message.reply_text("Session not found.")
            return
        flights = session.get("flights", [])
        flight_buttons = [
            InlineKeyboardButton(f"Flight {flight['flight_id']}", callback_data=f"flight:{session_id}:{flight['flight_id']}")
            for flight in flights
        ]
        reply_markup = InlineKeyboardMarkup([[button] for button in flight_buttons] + [[InlineKeyboardButton("<- Back", callback_data="home:1")]])
        await update.message.edit_text(menu_message_text(local_data, session_id), parse_mode='MarkdownV2', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error showing flights: {e}")

async def show_videos(update: Update, context: CallbackContext, session_id, flight_id, action=1):
    """
    Show the list of videos for a specific flight.
    """
    try:
        local_data = await load_local_data(update, context)
        session = next((s for s in local_data.get("sessions", []) if s["session_id"] == session_id), None)
        if not session:
            await update.message.reply_text("Session not found.")
            return
        flight = next((f for f in session["flights"] if f["flight_id"] == flight_id), None)
        if not flight:
            await update.message.reply_text("Flight not found.")
            return
        videos = flight.get("videos", [])
        video_buttons = [
            InlineKeyboardButton(f"{video['camera_name']}", callback_data=f"video:{session_id}:{flight_id}:{video['video_id']}")
            for video in videos
        ]
        reply_markup = InlineKeyboardMarkup([[button] for button in video_buttons] + [[InlineKeyboardButton("<- Back", callback_data=f"session:{session_id}")]])
        if action == 1:
            await update.message.edit_text(menu_message_text(local_data, session_id, flight_id), parse_mode='MarkdownV2', reply_markup=reply_markup)
        elif action == 0:
            await update.message.delete()
            await update.message.reply_text(menu_message_text(local_data, session_id, flight_id), parse_mode='MarkdownV2', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error showing videos: {e}")

async def open_video(update: Update, context: CallbackContext, session_id, flight_id, video_id):
    """
    Open and display a specific video.
    """
    try:
        session, flight, video = await find_video(update, context, session_id, flight_id, video_id)
        if not video:
            await update.message.reply_text("Video not found.")
            return
        back_markup = InlineKeyboardMarkup([[InlineKeyboardButton("<- Back", callback_data=f"flight:{session_id}:{flight_id}:0")]])
        await context.bot.send_video(chat_id=update.message.chat_id, video=video["file_id"], reply_markup=back_markup)
        await update.message.delete()
    except Exception as e:
        logger.error(f"Error opening video: {e}")
        await update.message.reply_text(f"Failed to send video: {str(e)}")


# Ifly chat functions
async def ask_for_username(update: Update, context: CallbackContext):
    # prompts user with username to upload videos to
    try:
        text = "To upload videos - please send your username"
        await context.bot.edit_message_text(text, IFLY_CHAT_ID, await ifly_menu_message_id(context))
    except Exception as e:
        logger.error(f"Error ask_for_username: {e}")
        raise

async def check_username(update: Update, context: CallbackContext):
    # check if username exists among users and sends a confirmation message
    try:
        if check_ifly_chat_state("no"):
            data = load_system_data()
            await update.message.delete()
            
            users = data.users
            chat_id = None
            
            for user in users:
                if str(user.username).lower() == update.message.text.lower().replace('@','').replace("t.me/",''):
                    logger.info(f"Found user. Chat_id = {user.chat_id}")
                    chat_id = user.chat_id
                    username = user.username
                    break
            
            # send auth message
            if chat_id:
                text = "Please, confirm your\nauthentification attempt"
                keyboard = [
                    [
                        InlineKeyboardButton("❌", callback_data="auth:0"),
                        InlineKeyboardButton("✅", callback_data="auth:1"),
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                auth_message = await context.bot.send_message(chat_id, text, reply_markup=reply_markup)
                
                
                text = "To upload videos - please send your username\n\nPlease, confirm authentification from your Telegram account"
                keyboard = [
                    [
                        InlineKeyboardButton("Cancel", callback_data=f"cancel_auth:{chat_id}:{auth_message.message_id}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.edit_message_text(text, IFLY_CHAT_ID, await ifly_menu_message_id(context), reply_markup=reply_markup)
                
                data.ifly_chat.session.username = username
                data.ifly_chat.session.chat_id = chat_id
                data.ifly_chat.session.ends = int(datetime.now().timestamp())
                
                save_system_data(data)
                update_ifly_chat_state("yes")
            else:
                text = "To upload videos - please send your username\n\nUsername not found. Please, try again"
                await context.bot.edit_message_text(text, IFLY_CHAT_ID, await ifly_menu_message_id(context))
                                    
    except Exception as e:
        logger.error(f"Error ask_for_username: {e}")
        raise

async def start_session(update: Update, context: CallbackContext, confiramtion):
    # upon recieving confirmation - starting session
    # when session ends - updates menu massage to reflect that
    try:
        await update.message.delete()
        logger.info(confiramtion)
        if confiramtion == 0:
            text = "To upload videos - please send your username\n\nAuthentification was rejected. Please, try again"
            await context.bot.edit_message_text(text, IFLY_CHAT_ID, await ifly_menu_message_id(context))
            update_ifly_chat_state("no")
        elif confiramtion == 1:
            data = load_system_data()
            text = f"Hi, {data.ifly_chat.session.username}!\nUpload your videos"
            keyboard = [
                [
                    InlineKeyboardButton("Logout", callback_data=f"end_session")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.edit_message_text(text, IFLY_CHAT_ID, await ifly_menu_message_id(context), reply_markup=reply_markup)
            data.ifly_chat.session.ends = int(datetime.now().timestamp()) + 900
            save_system_data(data)
                
    except Exception as e:
        logger.error(f"Error ask_for_username: {e}")
        raise

async def ifly_inline_buttons(update: Update, context: CallbackContext, query):
    # upon recieving confirmation - starting session
    # when session ends - updates menu massage to reflect that
    try:
        parts = query.data.split(':')
        logger.info(parts)
        if parts[0] == "cancel_auth":
            await context.bot.delete_message(parts[1], parts[2])
            
            text = "To upload videos - please send your username"
            await context.bot.edit_message_text(text, IFLY_CHAT_ID, await ifly_menu_message_id(context))
            update_ifly_chat_state("no")
        elif parts[0] == "end_session":
            text = "To upload videos - please send your username"
            await context.bot.edit_message_text(text, IFLY_CHAT_ID, await ifly_menu_message_id(context))
            update_ifly_chat_state("no")

                
    except Exception as e:
        logger.error(f"Error ask_for_username: {e}")
        raise


def main():
    """
    Main function to start the Telegram bot.
    """
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help))
    # application.add_handler(CommandHandler("list", list))
    application.add_handler(CommandHandler("clear_data", clear_local_data))
    application.add_handler(CommandHandler("show_data", show_local_data))
    application.add_handler(CommandHandler("create_storage", create_storage_message))
    application.add_handler(MessageHandler(filters.VIDEO, upload_video))
    application.add_handler(MessageHandler(filters.User(user_id=IFLY_CHAT_ID), check_username))
    application.add_handler(MessageHandler(filters.Document.FileExtension("json"), edit_local_data))
    application.add_handler(CallbackQueryHandler(inline_button))

    application.run_polling()

if __name__ == "__main__":
    main()
