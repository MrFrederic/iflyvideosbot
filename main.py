import logging
import os
import io
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaDocument
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from dotenv import load_dotenv

load_dotenv('.env')

BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Storage functions
async def get_storage_message(update: Update, context: CallbackContext):
    chat = await context.bot.get_chat(update.message.chat_id)
    if chat.pinned_message:
        pinned_message = chat.pinned_message
        logger.info(f"Pinned message found")
    else:
        logger.info("No pinned message in this chat. Creating new storage message")
        pinned_message = await create_storage(update, context)
    return pinned_message

async def load_storage(update: Update, context: CallbackContext):
    try:
        message = await get_storage_message(update, context)
 
        if not message.document:
            logger.error(f"Pinned message doesn't contain document?")
            return None

        document = message.document
        file_info = await context.bot.get_file(document.file_id)
        byte_array = await file_info.download_as_bytearray()
        data = byte_array.decode('utf-8')
        return json.loads(data)
    except Exception as e:
        logger.error(f"Unknown error while loading storage: {e}")

async def save_storage(update: Update, context: CallbackContext, video_storage):
    try:
        file_buffer = io.BytesIO()
        file_buffer.write(json.dumps(video_storage).encode('utf-8'))
        file_buffer.seek(0)
        message = await get_storage_message(update, context)
        await message.edit_media( 
            media=InputMediaDocument(
                media=file_buffer,
                filename="video_storage.json",
                caption="This is a servise message. Please, do not delete or unpin it!"
            )
        )
        logger.info("Storage message updated.")
        return message
    except Exception as e:
        logger.error(f"Error updating storage message: {e}")


# Service Functions
def parse_filename(filename):
    filename = filename.replace('-', '_')
    parts = filename.split('_')
    logger.info(filename)
    if len(parts) < 7:
        raise ValueError("Filename format is incorrect")
    return {
        "camera_name": parts[2],
        "flight_number": int(parts[3]),
        "date": "_".join(parts[4:7])
    }

def generate_unique_id(storage, key="session_id"):
    current_ids = [item[key] for item in storage]
    return max(current_ids, default=0) + 1

def get_or_create_session(video_storage, date):
    session = next((s for s in video_storage["sessions"] if s["date"] == date), None)
    if session:
        return session
    new_session = {"session_id": generate_unique_id(video_storage["sessions"]), "date": date, "flights": []}
    video_storage["sessions"].append(new_session)
    video_storage["sessions"].sort(key=lambda s: datetime.strptime(s["date"], '%Y_%m_%d'))
    for idx, session in enumerate(video_storage["sessions"]):
        session["session_id"] = idx + 1
    return new_session

def get_or_create_flight(session, flight_number, length=None):
    logger.info("LOOKING FOR FLIGHT")
    logger.info(flight_number)
    for flight in session["flights"]:
        logger.info(flight["flight_id"])
        if flight["flight_id"] == flight_number:
            return flight
    new_flight = {"flight_id": flight_number, "videos": [], "length": length}
    session["flights"].append(new_flight)
    return new_flight

def menu_message_text(video_storage, current_session=None, current_flight=None):
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

async def find_video(update: Update, context: CallbackContext, session_id, flight_id, video_id):
    video_storage = await load_storage(update, context)
    session = next((s for s in video_storage.get("sessions", []) if s["session_id"] == session_id), None)
    if not session:
        return None, None, None
    flight = next((f for f in session["flights"] if f["flight_id"] == flight_id), None)
    if not flight:
        return session, None, None
    video = next((v for v in flight.get("videos", []) if v["video_id"] == video_id), None)
    if not video:
        return session, flight, None
    return session, flight, video

# Command handlers
async def create_storage(update: Update, context: CallbackContext) -> None:
    video_storage = {"sessions": []}
    file_buffer = io.BytesIO()
    file_buffer.write(json.dumps(video_storage).encode('utf-8'))
    file_buffer.seek(0)
    message = await context.bot.send_document(
        chat_id=update.message.chat_id,
        document=file_buffer,
        filename="video_storage.json",
        caption="This is a servise message. Please, do not delete or unpin it!"
    )
    await message.pin(disable_notification=True)
    logger.info(f"Storage message created and pinned")
    return message

async def clear_storage(update: Update, context: CallbackContext) -> None:
    video_storage = {"sessions": []}
    await save_storage(update, context, video_storage)
    await update.message.reply_text("All stored videos have been cleared.")
    
async def show_storage(update: Update, context: CallbackContext) -> None:
    video_storage = await load_storage(update, context)
    logging.info("video_storage contents:")
    logging.info(json.dumps(video_storage, indent=4))

async def start(update: Update, context: CallbackContext) -> None:
    message = "Welcome to the Bodyflight Video Bot! Use /list to see your videos."
    await update.message.delete()
    await update.message.reply_text(message)

async def list(update: Update, context: CallbackContext) -> None:
    await update.message.delete()
    await show_sessions(update, context, edit=1)


# Json file handling (aka updating videon_storage)
async def edit_storage(update: Update, context: CallbackContext):
    try:
        message = update.message
        if not message.document:
            logger.error(f"Message doesn't contain document?")
            return None

        document = message.document
        file_info = await context.bot.get_file(document.file_id)
        logger.info(file_info)
        byte_array = await file_info.download_as_bytearray()
        data = byte_array.decode('utf-8')
        video_storage = json.loads(data)
        await save_storage(update, context, video_storage)
        logger.info("Storage updated manually")
        await message.delete()
    except Exception as e:
        logger.error(f"Unknown error while editing storage: {e}")


# Video handling (aka uploading video)
async def upload_video(update: Update, context: CallbackContext) -> None:
    video_storage = await load_storage(update, context)
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

    session = get_or_create_session(video_storage, date)
    flight = get_or_create_flight(session, flight_number, file_duration)

    # Check if a video with the same filename already exists
    existing_video = any(existing["filename"] == file_name for existing in flight["videos"])

    if not existing_video:
        video_id = generate_unique_id(flight["videos"], key="video_id")
        flight["videos"].append({
        "video_id": video_id,
        "filename": file_name,
        "camera_name": camera_name,
        "file_id": file_id
        })
        await save_storage(update, context, video_storage)
    else:
        logger.info(f"Ignoring duplicate video with filename: {file_name}")
    await update.message.delete()
    logger.info(f"Deleted the original video message.")


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
            "video": open_video,
        }.get(parts[0])
        if handler:
            await handler(query, context, *map(int, parts[1:]))
    except Exception as e:
        logger.error(f"Error handling callback data: {e}")
        await query.message.reply_text(f"An error occurred while processing button: {e}")


# Menu display functions
async def show_sessions(update: Update, context: CallbackContext, edit=0) -> None:
    video_storage = await load_storage(update, context)
    sessions = video_storage.get("sessions", [])
    if not sessions:
        text = "No sessions found"
    else:
        text = menu_message_text(video_storage)
        session_buttons = [InlineKeyboardButton(f"Session {session['session_id']}", callback_data=f"session:{session['session_id']}") for session in sessions]
        reply_markup = InlineKeyboardMarkup([[button] for button in session_buttons])
    if edit == 1:
        await update.message.edit_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)

async def show_flights(update: Update, context: CallbackContext, session_id) -> None:
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

async def show_videos(update: Update, context: CallbackContext, session_id, flight_id, action=1) -> None:
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

async def open_video(update: Update, context: CallbackContext, session_id, flight_id, video_id) -> None:
    session, flight, video = await find_video(update, context, session_id, flight_id, video_id)
    if not video:
        await update.message.reply_text("Video not found.")
        return
    try:
        back_markup = InlineKeyboardMarkup([[InlineKeyboardButton("<- Back", callback_data=f"flight:{session_id}:{flight_id}:0")]])
        await context.bot.send_video(chat_id=update.message.chat_id, video=video["file_id"], reply_markup=back_markup)
        await update.message.delete()
    except Exception as e:
        await update.message.reply_text(f"Failed to send video: {str(e)}")


def main() -> None:
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