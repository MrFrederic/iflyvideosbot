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


# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


# Storage functions
async def get_storage_message(update: Update, context: CallbackContext):
    """
    Retrieve the pinned message in the chat to use as storage. If none exists, create a new one.
    """
    try:
        chat = await context.bot.get_chat(update.message.chat_id)
        if chat.pinned_message:
            pinned_message = chat.pinned_message
            logger.info("Pinned message found")
        else:
            logger.info("No pinned message in this chat. Creating new storage message")
            pinned_message = await create_storage(update, context)
        return pinned_message
    except Exception as e:
        logger.error(f"Error retrieving storage message: {e}")
        return None

async def load_storage(update: Update, context: CallbackContext):
    """
    Load the JSON storage from the pinned message document.
    """
    try:
        message = await get_storage_message(update, context)
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

async def save_storage(update: Update, context: CallbackContext, video_storage):
    """
    Save the video storage JSON data to the pinned message document.
    """
    try:
        file_buffer = io.BytesIO()
        file_buffer.write(json.dumps(video_storage).encode('utf-8'))
        file_buffer.seek(0)
        message = await get_storage_message(update, context)
        if not message:
            logger.error("No storage message available to save data")
            return None
        await message.edit_media(
            media=InputMediaDocument(
                media=file_buffer,
                filename="video_storage.json",
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

def get_or_create_session(video_storage, date):
    """
    Retrieve or create a new session based on the provided date.
    """
    try:
        for session in video_storage["sessions"]:
            if session["date"] == date:
                return session
        
        new_session = {
            "session_id": generate_unique_id(video_storage["sessions"]),
            "date": date,
            "flights": []
        }
        video_storage["sessions"].append(new_session)
        video_storage["sessions"].sort(key=lambda s: datetime.strptime(s["date"], '%Y_%m_%d'))
        for idx, session in enumerate(video_storage["sessions"]):
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

def menu_message_text(video_storage, current_session=None, current_flight=None):
    """
    Generate the menu message text for the current video storage state.
    """
    try:
        message = []
        
        sessions = video_storage.get("sessions", [])
        
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
        video_storage = await load_storage(update, context)
        session = next((s for s in video_storage.get("sessions", []) if s["session_id"] == session_id), None)
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

def total_flight_time(video_storage):
    """
    Calculate the total flight time across all sessions.
    """
    total_time = 0
    for session in video_storage["sessions"]:
        for flight in session["flights"]:
            total_time += flight["length"]
    return total_time

def days_since_first_session(video_storage):
    """
    Calculate the number of days since the first session.
    """
    if not video_storage["sessions"]:
        return 0

    # Find the earliest date in the sessions
    earliest_date_str = min(session["date"] for session in video_storage["sessions"])
    earliest_date = datetime.strptime(earliest_date_str, "%Y_%m_%d")
    
    # Calculate the number of days since the earliest session
    current_date = datetime.now()
    days_since_first = (current_date - earliest_date).days
    
    return days_since_first


# Command handlers
async def create_storage(update: Update, context: CallbackContext):
    """
    Create a new storage message and pin it in the chat.
    """
    try:
        video_storage = {"sessions": []}
        file_buffer = io.BytesIO()
        file_buffer.write(json.dumps(video_storage).encode('utf-8'))
        file_buffer.seek(0)
        message = await context.bot.send_document(
            chat_id=update.message.chat_id,
            document=file_buffer,
            filename="video_storage.json",
            caption="This is a service message. Please, do not delete or unpin it!"
        )
        await message.pin(disable_notification=True)
        logger.info("Storage message created and pinned")
        return message
    except Exception as e:
        logger.error(f"Error creating storage message: {e}")
        return None

async def clear_storage(update: Update, context: CallbackContext):
    """
    Clear the storage by resetting it to an empty state.
    """
    try:
        video_storage = {"sessions": []}
        await save_storage(update, context, video_storage)
        await update.message.reply_text("All stored videos have been cleared.")
    except Exception as e:
        logger.error(f"Error clearing storage: {e}")

async def show_storage(update: Update, context: CallbackContext):
    """
    Display the contents of the storage.
    """
    try:
        video_storage = await load_storage(update, context)
        logger.info("Video storage contents:")
        logger.info(json.dumps(video_storage, indent=4))
    except Exception as e:
        logger.error(f"Error showing storage: {e}")

async def start(update: Update, context: CallbackContext, edit=0):
    try:
        await update.message.delete()
        await show_start_menu(update, context, edit=1)
    except Exception as e:
        logger.error(f"Error start command: {e}")
    
async def list(update: Update, context: CallbackContext):
    try:
        await update.message.delete()
        await show_sessions(update, context, edit=1)
    except Exception as e:
        logger.error(f"Error list command: {e}")


# JSON file handling (aka updating video storage)
async def edit_storage(update: Update, context: CallbackContext):
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
        video_storage = json.loads(data)
        await save_storage(update, context, video_storage)
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
        video_storage = await load_storage(update, context)
        video = update.message.video
        file_id = video.file_id
        file_name = video.file_name
        file_duration = round(video.duration / 5) * 5

        video_info = parse_filename(file_name)
        date = video_info['date']
        flight_number = int(video_info['flight_number'])
        camera_name = video_info['camera_name']
        logger.info(f"Received video: file_id={file_id}, file_name={file_name}, duration={file_duration}s")

        session = get_or_create_session(video_storage, date)
        flight = get_or_create_flight(session, flight_number, file_duration)

        # Check for duplicate video across all flights in all sessions
        duplicate_found = any(
            video["filename"] == file_name
            for session in video_storage["sessions"]
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
            await save_storage(update, context, video_storage)
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
    query = update.callback_query
    await query.answer()
    try:
        parts = query.data.split(':')
        handler = {
            "start": show_start_menu,
            "stats": show_statistics,
            "home": show_sessions,
            "session": show_flights,
            "flight": show_videos,
            "video": open_video,
        }.get(parts[0])
        if handler:
            await handler(query, context, *map(int, parts[1:]))
    except Exception as e:
        logger.error(f"Error handling callback data: {e}")
        await query.message.reply_text(f"An error occurred while processing button: {e}")


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
            await update.message.delete()
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
        video_storage = await load_storage(update, context)
        flight_time = "You have flown for " + format_flight_time(total_flight_time(video_storage))
        days_flown = "You started flying " + format_days_count(days_since_first_session(video_storage)) + " ago"
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
        video_storage = await load_storage(update, context)
        sessions = video_storage.get("sessions", [])
        if not sessions:
            text = "No sessions found"
        else:
            text = menu_message_text(video_storage)
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
        video_storage = await load_storage(update, context)
        session = next((s for s in video_storage.get("sessions", []) if s["session_id"] == session_id), None)
        if not session:
            await update.message.reply_text("Session not found.")
            return
        flights = session.get("flights", [])
        flight_buttons = [
            InlineKeyboardButton(f"Flight {flight['flight_id']}", callback_data=f"flight:{session_id}:{flight['flight_id']}")
            for flight in flights
        ]
        reply_markup = InlineKeyboardMarkup([[button] for button in flight_buttons] + [[InlineKeyboardButton("<- Back", callback_data="home:1")]])
        await update.message.edit_text(menu_message_text(video_storage, session_id), parse_mode='MarkdownV2', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error showing flights: {e}")

async def show_videos(update: Update, context: CallbackContext, session_id, flight_id, action=1):
    """
    Show the list of videos for a specific flight.
    """
    try:
        video_storage = await load_storage(update, context)
        session = next((s for s in video_storage.get("sessions", []) if s["session_id"] == session_id), None)
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
            await update.message.edit_text(menu_message_text(video_storage, session_id, flight_id), parse_mode='MarkdownV2', reply_markup=reply_markup)
        elif action == 0:
            await update.message.delete()
            await update.message.reply_text(menu_message_text(video_storage, session_id, flight_id), parse_mode='MarkdownV2', reply_markup=reply_markup)
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


def main():
    """
    Main function to start the Telegram bot.
    """
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", list))
    application.add_handler(CommandHandler("clear_storage", clear_storage))
    application.add_handler(CommandHandler("show_storage", show_storage))
    application.add_handler(CommandHandler("create_storage", create_storage))
    application.add_handler(MessageHandler(filters.VIDEO, upload_video))
    application.add_handler(MessageHandler(filters.Document.FileExtension("json"), edit_storage))
    application.add_handler(CallbackQueryHandler(inline_button))

    application.run_polling()

if __name__ == "__main__":
    main()
