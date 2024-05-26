import logging
import os
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, InputMediaDocument
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from dotenv import load_dotenv


load_dotenv('credentials.env')

BOT_TOKEN = os.getenv("BOT_TOKEN")
MAIN_ACCOUNT_ID = int(os.getenv("MAIN_ACCOUNT_ID", 0))
SECONDARY_ACCOUNT_ID = int(os.getenv("SECONDARY_ACCOUNT_ID", 0))
STORAGE_MESSAGE_ID = os.getenv("STORAGE_MESSAGE_ID")

if not BOT_TOKEN or not MAIN_ACCOUNT_ID or not SECONDARY_ACCOUNT_ID:
    raise ValueError("Required environment variables are missing.")


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants and global variables
STORAGE_FILE = 'video_storage.json'
video_storage = {}

# Storage functions
def load_storage():
    try:
        with open(STORAGE_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"sessions": []}

def save_storage():
    with open(STORAGE_FILE, 'w') as f:
        json.dump(video_storage, f, indent=4)

async def update_storage_message(context: CallbackContext):
    save_storage()
    if STORAGE_MESSAGE_ID:
        await edit_storage_message(context)
    else:
        await create_storage_message(context)

async def edit_storage_message(context: CallbackContext):
    try:
        with open(STORAGE_FILE, 'rb') as f:
            media = InputMediaDocument(f, filename=STORAGE_FILE)
            await context.bot.edit_message_media(
                chat_id=SECONDARY_ACCOUNT_ID, message_id=int(STORAGE_MESSAGE_ID), media=media
            )
            logger.info("Storage message updated.")
    except Exception as e:
        logger.error(f"Error updating storage message: {e}")

async def create_storage_message(context: CallbackContext):
    try:
        with open(STORAGE_FILE, 'rb') as f:
            msg = await context.bot.send_document(chat_id=SECONDARY_ACCOUNT_ID, document=InputFile(f, STORAGE_FILE))
            logger.info("Storage message created. Update STORAGE_MESSAGE_ID in the .env file.")
            logger.info("Storage message id =", msg.message_id)
    except Exception as e:
        logger.error(f"Error sending new storage message: {e}")

# Utility functions
def parse_filename(filename):
    filename = filename.replace('-', '_')
    parts = filename.split('_')
    logger.info(filename)
    if len(parts) < 7:
        raise ValueError("Filename format is incorrect")
    
    return {
        "camera_name": parts[2],
        "flight_number": parts[3],
        "date": "_".join(parts[4:7])
    }

def generate_unique_id(storage, key="session_id"):
    current_ids = [item[key] for item in storage]
    return max(current_ids, default=0) + 1

def get_or_create_session(date):
    global video_storage

    # Check if session already exists for the date
    session = next((s for s in video_storage["sessions"] if s["date"] == date), None)
    if session:
        return session

    # Create a new session if it doesn't exist
    new_session = {"session_id": generate_unique_id(video_storage["sessions"]), "date": date, "flights": []}
    video_storage["sessions"].append(new_session)

    # Sort sessions by date
    video_storage["sessions"].sort(key=lambda s: datetime.strptime(s["date"], '%Y_%m_%d'))

    # Re-assign session IDs after sorting to maintain correct order
    for idx, session in enumerate(video_storage["sessions"]):
        session["session_id"] = idx + 1

    return new_session

def get_or_create_flight(session, flight_number, length=None):
    for flight in session["flights"]:
        if flight["flight_id"] == flight_number:
            return flight
    new_flight = {"flight_id": generate_unique_id(session["flights"], key="flight_id"), "videos": [], "length": length}
    session["flights"].append(new_flight)
    return new_flight

def menu_message_text(current_session=None, current_flight=None):
    message = []
    sessions = video_storage.get("sessions", [])

    session = next((s for s in sessions if s["session_id"] == current_session), None)
    flights = session.get("flights", []) if session else []
    
    flight = next((f for f in flights if f["flight_id"] == current_flight), None)
    videos = flight.get("videos", []) if flight else []

    for s in sessions:
        message.append(f"- Session {s['session_id']} : {s['date']}")
        if s == session:
            for f in flights:
                message.append(f"- - Flight {f['flight_id']}: {f['length']} min")
                if f == flight:
                    for v in videos:
                        message.append(f"- - - {v['camera_name']}")

    return "\n".join(message)

# Command handlers
async def start(update: Update, _: CallbackContext) -> None:
    message = "Welcome to the Bodyflight Video Bot! Use /list to see your videos." if update.effective_chat.id == MAIN_ACCOUNT_ID else "Please, send videos here"
    await update.message.delete()
    await update.message.reply_text(message)

async def clear_storage(update: Update, context: CallbackContext) -> None:
    global video_storage
    if update.effective_chat.id != MAIN_ACCOUNT_ID:
        return
    video_storage = {"sessions": []}
    await update_storage_message(context)
    await update.message.reply_text("All stored videos have been cleared.")

async def show_storage(update: Update, _: CallbackContext) -> None:
    if update.effective_chat.id != MAIN_ACCOUNT_ID:
        return
    logging.info("video_storage contents:")
    logging.info(json.dumps(video_storage, indent=4))

# Video handling
async def handle_video(update: Update, context: CallbackContext) -> None:
    if update.effective_chat.id != MAIN_ACCOUNT_ID:
        return

    video = update.message.video
    file_id = video.file_id
    file_name = video.file_name
    file_duration = round(video.duration / 5) * 5

    try:
        video_info = parse_filename(file_name)
    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    date = video_info['date']
    flight_number = int(video_info['flight_number'])
    camera_name = video_info['camera_name']

    logger.info(f"Received video: file_id={file_id}, file_name={file_name}, duration={file_duration}s")

    session = get_or_create_session(date)
    flight = get_or_create_flight(session, flight_number, file_duration)
    
    if not any(video["filename"] == file_name for video in flight["videos"]):
        video_id = generate_unique_id(flight["videos"], key="video_id")
        flight["videos"].append({
            "video_id": video_id,
            "filename": file_name,
            "camera_name": camera_name,
            "file_id": file_id
        })

    try:
        await context.bot.forward_message(
            chat_id=SECONDARY_ACCOUNT_ID, from_chat_id=MAIN_ACCOUNT_ID, message_id=update.message.message_id
        )
        await update_storage_message(context)
        await context.bot.delete_message(chat_id=MAIN_ACCOUNT_ID, message_id=update.message.message_id)
        logger.info(f"Deleted the original video message from chat with ID {MAIN_ACCOUNT_ID}.")
    except Exception as e:
        logger.error(f"Error forwarding or deleting video: {e}")
        await update.message.reply_text(f"Error forwarding or deleting video: {e}")

# Inline button handling
async def inline_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    try:
        parts = query.data.split(':')
        handler = {
            "home": show_sessions,
            "session": show_flights,
            "flight": show_videos,
            "video": show_video,
        }.get(parts[0])

        if handler:
            await handler(query, context, *map(int, parts[1:]))
    except Exception as e:
        logger.error(f"Error handling callback data: {e}")
        await query.message.reply_text(f"An error occurred: {e}")

# Menu display functions
async def show_sessions(update: Update, _: CallbackContext, edit=0) -> None:
    sessions = video_storage.get("sessions", [])
    if not sessions:
        await update.message.reply_text("No videos stored yet.")
        return

    session_buttons = [InlineKeyboardButton(f"Session {session['session_id']}", callback_data=f"session:{session['session_id']}") for session in sessions]
    reply_markup = InlineKeyboardMarkup([[button] for button in session_buttons])

    if edit == 1:
        await update.message.edit_text(menu_message_text(), reply_markup=reply_markup)
    else:
        await update.message.reply_text(menu_message_text(), reply_markup=reply_markup)
        await update.message.delete()

async def show_flights(query, _: CallbackContext, session_id) -> None:
    session = next((s for s in video_storage.get("sessions", []) if s["session_id"] == session_id), None)
    if not session:
        await query.message.reply_text("Session not found.")
        return
    
    flights = session.get("flights", [])
    flight_buttons = [
        InlineKeyboardButton(f"Flight {flight['flight_id']}", callback_data=f"flight:{session_id}:{flight['flight_id']}")
        for flight in flights
    ]
    
    reply_markup = InlineKeyboardMarkup([[button] for button in flight_buttons] + [[InlineKeyboardButton("<- Back", callback_data="home:1")]])
    await query.message.edit_text(menu_message_text(session_id), reply_markup=reply_markup)

async def show_videos(query, _: CallbackContext, session_id, flight_id, action=1) -> None:
    session = next((s for s in video_storage.get("sessions", []) if s["session_id"] == session_id), None)
    if not session:
        await query.message.reply_text("Session not found.")
        return
    
    flight = next((f for f in session["flights"] if f["flight_id"] == flight_id), None)
    if not flight:
        await query.message.reply_text("Flight not found.")
        return

    videos = flight.get("videos", [])
    video_buttons = [
        InlineKeyboardButton(f"{video['camera_name']}", callback_data=f"video:{session_id}:{flight_id}:{video['video_id']}")
        for video in videos
    ]
    
    reply_markup = InlineKeyboardMarkup([[button] for button in video_buttons] + [[InlineKeyboardButton("<- Back", callback_data=f"session:{session_id}")]])
    if action == 1:
        await query.message.edit_text(menu_message_text(session_id, flight_id), reply_markup=reply_markup)
    elif action == 0:
        await query.message.delete()
        await query.message.reply_text(menu_message_text(session_id, flight_id), reply_markup=reply_markup)

async def show_video(query, context: CallbackContext, session_id, flight_id, video_id) -> None:
    session, flight, video = find_video(session_id, flight_id, video_id)
    if not video:
        await query.message.reply_text("Video not found.")
        return

    try:
        back_markup = InlineKeyboardMarkup([[InlineKeyboardButton("<- Back", callback_data=f"flight:{session_id}:{flight_id}:0")]])
        await context.bot.send_video(chat_id=query.message.chat_id, video=video["file_id"], reply_markup=back_markup)
        await query.message.delete()
    except Exception as e:
        await query.message.reply_text(f"Failed to send video: {str(e)}")

# Helper function to find video
def find_video(session_id, flight_id, video_id):
    session = next((s for s in video_storage.get("sessions", []) if s["session_id"] == session_id), None)
    if not session:
        return None, None, None

    flight = next((f for f in session["flights"] if f["flight_id"] == flight_id), None)
    if not flight:
        return session, None, None
    
    video = next((v for v in flight.get("videos", []) if v["video_id"] == video_id), None)
    return session, flight, video

# Main function
def main() -> None:
    global video_storage
    video_storage = load_storage()

    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", show_sessions))
    application.add_handler(CommandHandler("clear", clear_storage))
    application.add_handler(CommandHandler("show_storage", show_storage))
    application.add_handler(MessageHandler(filters.VIDEO & filters.User(user_id=MAIN_ACCOUNT_ID), handle_video))
    application.add_handler(CallbackQueryHandler(inline_button))

    application.run_polling()

if __name__ == "__main__":
    main()