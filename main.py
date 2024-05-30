from dotmap import DotMap
import logging
import os
import io
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaDocument, Chat
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from dotenv import load_dotenv


# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
log = logging.getLogger(__name__)


# Load environment variables
try:
    load_dotenv('.env')
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    IFLY_CHAT_ID = int(os.getenv("IFLY_CHAT_ID"))
except Exception:
        log.error(f"Error setting environment variables! Please, check your .env file")
    
SYSTEM_DATA_FILE = "data.json"


# Storage functions
async def get_storage_message(update: Update, context: CallbackContext, chat_id=None):
    """
    Retrieve the pinned message in the chat to use as storage. If none exists, create a new one.
    """
    if not chat_id:
        chat_id = update.message.chat_id
    
    try:
        chat: Chat = await context.bot.get_chat(chat_id)
        add_or_update_user(update, chat_id, chat.username)
        if chat.pinned_message:
            pinned_message = chat.pinned_message
            log.info("Pinned message found")
        else:
            log.info("No pinned message in this chat. Creating new storage message")
            pinned_message = await create_storage_message(update, context, chat_id)
        return pinned_message
    except Exception as e:
        log.error(f"Error retrieving storage message: {e}")
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
            log.error("Pinned message doesn't contain document")
            return None

        file_info = await context.bot.get_file(message.document.file_id)
        byte_array = await file_info.download_as_bytearray()
        data_dict = json.loads(byte_array.decode('utf-8'))
        data = DotMap(data_dict)
        return data
    except Exception as e:
        log.error(f"Error while loading storage: {e}")
        return None

async def save_local_data(update: Update, context: CallbackContext, local_data, chat_id=None):
    """
    Save the video storage JSON data to the pinned message document.
    """
    if not chat_id:
        chat_id = update.message.chat_id
    try:
        # Ensure local_data is a DotMap instance before converting
        if isinstance(local_data, DotMap):
            data_dict = local_data.toDict()
        else:
            data_dict = local_data

        json_local_data = json.dumps(data_dict, indent=4).encode('utf-8')

        # Properly handle the file buffer
        file_buffer = io.BytesIO()
        file_buffer.write(json_local_data)
        file_buffer.seek(0)

        message = await get_storage_message(update, context, chat_id)
        if not message:
            log.error("No storage message available to save data to")
            return None

        await message.edit_media(
            media=InputMediaDocument(
                media=file_buffer,
                filename="data.json",
                caption="This is a service message. Do NOT delete or unpin it unless you want to lose your videos!"
            )
        )
        log.info("Storage message updated.")
        return message
    except Exception as e:
        log.error(f"Error updating storage message: {e}")
        return None


# Service Functions
def parse_filename(filename):
    """
    Parse the filename to extract camera name, session and date.
    """
    try:
        filename = filename.replace('-', '_')
        parts = filename.split('_')
        
        flight_number = parts[3]
        date = int(datetime.strptime('_'.join(parts[4:7]), '%Y_%m_%d').timestamp())
        time_slot = get_time_slot('_'.join(parts[7:9]))
        camera_name = parts[2]
        
        return date, time_slot, flight_number, camera_name
    except Exception as e:
        log.error(f"Error parsing filename: {e}")
        raise

def get_time_slot(input_time):
    hours, minutes = map(int, input_time.split('_'))
    
    if minutes < 30:
        minutes = 0
    else:
        minutes = 30

    formatted_time = "{:02d}:{:02d}".format(hours, minutes)
    
    return formatted_time


def generate_unique_video_id(local_data):
    """
    Generate a unique ID for sessions or videos in the storage.
    """
    try:
        max_id = 0
        for day in local_data.days:
            for session in day.sessions:
                for flight in session.flights:
                    for video in flight.videos:
                        max_id = max(max_id, video.video_id)
        return max_id + 1
    except Exception as e:
        log.error(f"Error generate_unique_video_id: {e}")
        raise

def get_or_create_day(local_data, date):
    """
    Retrieve or create a new session based on the provided date.
    """
    try:
        log.info(f"get_or_create_day date = {date}")
        for day in local_data.days:
            if day.date == date:
                log.info(f"found existing date")
                return day
        
        new_day = DotMap({
            "date": date,
            "sessions": []
        })
        
        for idx, day in enumerate(local_data.days):
            log.info(f"comparing {date} w {day.date}, idx = {idx}")
            if date < day.date:
                log.info(f"True")
                local_data.days.insert(idx, new_day)
                return local_data.days[idx]
        else:
            log.info(f"appending")
            local_data.days.append(new_day)
            return local_data.days[-1]
    except Exception as e:
        log.error(f"Error get_or_create_day: {e}")
        raise

def get_or_create_session(day, time_slot):
    """
    Retrieve or create a new session based on the provided date.
    """
    try:
        for session in day.sessions:
            if session.time_slot == time_slot:
                return session
        
        new_session = DotMap({
            "time_slot": time_slot,
            "flights": []
        })
        
        for idx, session in enumerate(day.sessions):
            if datetime.strptime(time_slot, "%H:%M") < datetime.strptime(session.time_slot, "%H:%M"):
                day.sessions.insert(idx, new_session)
                return day.sessions[idx]
        else:
            day.sessions.append(new_session)
            return day.sessions[-1]
    except Exception as e:
        log.error(f"Error get_or_create_session: {e}")
        raise

def get_or_create_flight(session, flight_number, length):
    """
    Retrieve or create a new flight based on the provided flight number.
    """
    try:
        for flight in session.flights:
            if flight.flight_number == flight_number:
                return flight
        
        new_flight = DotMap({
            "length": length,
            "flight_number": flight_number,
            "videos": [],
        })
    
        for idx, flight in enumerate(session.flights):
            if flight_number < flight.flight_number:
                session.flights.insert(idx, new_flight)
                return session.flights[idx]
        else:
            session.flights.append(new_flight)
            return session.flights[-1]
    except Exception as e:
        log.error(f"Error getting or creating flight: {e}")
        raise


def generate_tree(local_data, day_p=None, session_p=None, flight_p=None):
    """
    Generate the menu message text for the current video storage state.
    """
    def format_date(timestamp):
        return datetime.fromtimestamp(timestamp).strftime('%d\.%m\.%Y')

    def format_flight_length(length):
        minutes, seconds = divmod(length, 60)
        return f"{minutes}\:{seconds:02d} min"
    
    try:
        tree_text = ["📦 *Library*"]
        
        days = local_data.days
        for index_d, day in enumerate(days):
            line = ["`"]
            
            if index_d + 1 == len(days): line.append(" ┗━` ")
            else: line.append(" ┣━` ")
            
            if day_p == index_d: line.append("📂 ")
            else: line.append("📁 ")

            if day_p == index_d: line.append(f"*")
            line.append(f"{format_date(day.date)}")
            if day_p == index_d: line.append(f"*")
            
            tree_text.append(''.join(line))
            if day_p == index_d:  
                sessions = day.sessions
                
                for index_s, session in enumerate(sessions):
                    if len(sessions) > 1:
                        line = ["`"]
                        
                        if index_d + 1 == len(days): line.append("   ")
                        else: line.append(" ┃ ")
                
                        if index_s + 1 == len(sessions): line.append(" ┗━` ")
                        else: line.append(" ┣━` ")
                        
                        if session_p == index_s: line.append("📂 ")
                        else: line.append("📁 ")
                        
                        if session_p == index_s: line.append(f"*")
                        line.append(f"Session {index_s + 1} ")
                        if session_p == index_s: line.append(f"*")
                        line.append(f"_\({session.time_slot}\)_")
                        
                        tree_text.append(''.join(line))  
                                   
                    if session_p == index_s:
                        flights = session.flights
                        for index_f, flight in enumerate(flights):
                            line = ["`"]
                    
                            if index_d + 1 == len(days): line.append("   ")
                            else: line.append(" ┃ ")

                            if len(sessions) > 1:
                                if index_s + 1 == len(sessions): line.append("   ")
                                else: line.append(" ┃ ")
                            
                            if index_f + 1 == len(flights): line.append(" ┗━` ")
                            else: line.append(" ┣━` ")
                            
                            if flight_p == index_f: line.append("📂 ")
                            else: line.append("📁 ")
                            
                            if flight_p == index_f: line.append(f"*")
                            line.append(f"Flight {flight.flight_number} ")
                            if flight_p == index_f: line.append(f"*")
                            line.append(f"_{format_flight_length(flight.length)}_")
                            
                            tree_text.append(''.join(line))
                            if flight_p == index_f:
                                videos = flight.videos
                                for index_v, video in enumerate(videos):
                                    line = ["`"]
                    
                                    if index_d + 1 == len(days): line.append("   ")
                                    else: line.append(" ┃ ")
                            
                                    if len(sessions) > 1:
                                        if index_s + 1 == len(sessions): line.append("   ")
                                        else: line.append(" ┃ ")
                                    
                                    if index_f + 1 == len(flights): line.append("   ")
                                    else: line.append(" ┃ ")
                                    
                                    if index_v + 1 == len(videos): line.append(" ┗━` ")
                                    else: line.append(" ┣━` ")
                                    
                                    line.append(f"📹 {video.camera_name}")
                                    
                                    tree_text.append(''.join(line))
        return "\n".join(tree_text)
    except Exception as e:
        log.error(f"Error generating menu message text: {e}")
        raise

def total_flight_time(local_data):
    """
    Calculate the total flight time across all sessions.
    """
    total_time = 0
    for day in local_data.days:
            for session in day.sessions:
                for flight in session.flights:
                    total_time += flight.length
    return total_time

def days_since_first_session(local_data):
    """
    Calculate the number of days since the first session.
    """
    if not local_data.days:
        return 0

    earliest_date = min(day.date for day in local_data.days)
    
    current_date = datetime.now().timestamp()
    days_since_first = (current_date - earliest_date) / 86400
    
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
        log.error(f"Error check_ifly_chat_state: {e}")
        raise

def update_ifly_chat_state(state):
    try:
        data = load_system_data()
        data.ifly_chat.session.status = state
        save_system_data(data)
    except Exception as e:
        log.error(f"Error update_ifly_chat_state: {e}")
        raise
    
async def ifly_menu_message_id(context: CallbackContext, restart=0):
    try: 
        data = load_system_data()
        
        message_id = data.ifly_chat.menu_message_id

        if message_id and restart == 1:
            await context.bot.delete_message(IFLY_CHAT_ID, message_id)
            message_id = None

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
        log.error(f"Error ifly_menu_message_id: {e}")
        raise
    
def add_or_update_user(update: Update, chat_id=None, username=None):
    try:
        data = load_system_data()
        
        if not chat_id:
            chat_id = update.message.chat_id
        
        if not username:
            username = update.message.from_user.username
        
        for user in data.users:
            if user.chat_id == chat_id:
                user.username = username
                save_system_data(data)
                return
        new_user = {"username": username, "chat_id": chat_id}
        data.users.append(new_user)
        save_system_data(data)
    except Exception as e:
        log.error(f"Error add_or_update_user: {e}")
        raise

async def delete_message(update: Update,context: CallbackContext, chat_id, message_id):
    await context.bot.delete_message(chat_id, message_id)

async def send_closable_message(update: Update, text): 
    message = await update.message.reply_text(text, parse_mode='MarkdownV2')
    reply_markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Close", callback_data=f"delete:{update.message.chat_id}:{message.message_id}")
            ]
        ])
    return await message.edit_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
    

# Command handlers
async def create_storage_message(update: Update, context: CallbackContext, chat_id=None):
    """
    Create a new storage message and pin it in the chat.
    """
    if not chat_id:
        chat_id = update.message.chat_id
    try:
        local_data = {"days": []}
        file_buffer = io.BytesIO()
        file_buffer.write(json.dumps(local_data).encode('utf-8'))
        file_buffer.seek(0)
        message = await context.bot.send_document(
            chat_id=chat_id,
            document=file_buffer,
            filename="data.json",
            caption="This is a service message. Do NOT delete or unpin it unless you want to lose your videos!"
        )
        await message.pin(disable_notification=True)
        log.info("Storage message created and pinned")
        return message
    except Exception as e:
        log.error(f"Error creating storage message: {e}")
        return None

async def clear_local_data(update: Update, context: CallbackContext):
    """
    Clear the storage by resetting it to an empty state.
    """
    try:
        await update.message.delete()
        local_data = {"days": []}
        
        await send_closable_message(update, "All stored videos have been cleared\.")
        
        await save_local_data(update, context, local_data)
    except Exception as e:
        log.error(f"Error clearing storage: {e}")

async def show_local_data(update: Update, context: CallbackContext):
    """
    Display the contents of the storage.
    """
    try:
        local_data = await load_local_data(update, context)
        log.info("Video storage contents:")
        log.info(json.dumps(local_data, indent=4))
    except Exception as e:
        log.error(f"Error showing storage: {e}")

async def start(update: Update, context: CallbackContext, edit=0):
    try:
        await update.message.delete()
        if update.message.chat_id == IFLY_CHAT_ID:
            await ask_for_username(update, context, 1)
        else:
            add_or_update_user(update)
            await show_start_menu(update, context)
    except Exception as e:
        log.error(f"Error start command: {e}")
        
async def help(update: Update, context: CallbackContext):
    try:
        await update.message.delete()
        if update.message.chat_id == IFLY_CHAT_ID:
            text = """You can send your videos to your bot after completing authentification"""
        else:
            text = """Awailable commands\:\n\/start \- Shows menu\n\/help \- Shows this message\n\/info \- Shows info message\n\/clear\_data \- Carefull\!\!\! Delets all saved videos\!\n\nTo upload videos \- just drop them here\. Bot will automatically find their correct flight\. Alternetively, you can send them from \@iFLYvideo account after completing authentification\."""

        await send_closable_message(update, text)
    except Exception as e:
        log.error(f"Error help command: {e}")


# JSON file handling (aka updating video storage)
async def edit_local_data(update: Update, context: CallbackContext): 
    """
    Edit the storage by updating it with a new JSON file.
    """
    try:
        message = update.message
        if not message.document:
            log.error("Message doesn't contain document")
            return None

        file_info = await context.bot.get_file(message.document.file_id)
        byte_array = await file_info.download_as_bytearray()
        data = byte_array.decode('utf-8')
        local_data = json.loads(data)
        await save_local_data(update, context, local_data)
        await send_closable_message(update, "Storage replaced")
        await message.delete()
    except Exception as e:
        log.error(f"Error editing storage: {e}")


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
        length = round(video.duration / 5) * 5

        date, time_slot, flight_number, camera_name = parse_filename(file_name)

        log.info(f"Received video: file_id={file_id}, file_name={file_name}, length={length}s, date={date}, time_slot={time_slot}, flight_number={flight_number}, camera_name={camera_name}")

        # day = get_or_create_day(local_data, date)
        # session = get_or_create_session(day, time_slot)
        # flight = get_or_create_flight(session, flight_number, length)
        
        flight = get_or_create_flight(get_or_create_session(get_or_create_day(local_data, date), time_slot), flight_number, length)
        
        # Check for duplicate video across all flights in all sessions
        duplicate_found = any(
            video.file_name == file_name
            for day in local_data.days
            for session in day.sessions
            for flight in session.flights
            for video in flight.videos
        )

        if not duplicate_found:
            video_id = generate_unique_video_id(local_data)
            flight.videos.append({
                "video_id": video_id,
                "camera_name": camera_name,
                "file_name": file_name,
                "file_id": file_id
            })
            await save_local_data(update, context, local_data, chat_id)
            log.info(f"Video {file_name} added successfully.")
        else:
            log.info(f"Ignoring duplicate video with filename: {file_name}")
            pass
        await update.message.delete()
    except Exception as e:
        log.error(f"Error upload_video: {e}")


# Inline button handling
async def inline_button(update: Update, context: CallbackContext): # Update handlers for new menu message function
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
            log.info(parts)
            handler = {
                "home": show_start_menu,
                "stats": show_statistics,
                "nav": navigate_tree,
                "video": open_video,
                "auth": start_session,
                "delete": delete_message
            }.get(parts[0])
            if handler:
                await handler(query, context, *map(int, parts[1:]))
    except Exception as e:
        log.error(f"Error handling callback data: {e}")
        # await query.message.reply_text(f"An error occurred while processing button: {e}")


# Menu display functions
async def show_start_menu(update: Update, context: CallbackContext, edit=0):
    """
    Start menu
    """
    try:
        text = "🏠 Welcome to the *iFLY Video Storage Bot*\!\nUse buttons to navigate\."
        keyboard = [
            [
                InlineKeyboardButton("🎥 Browse Videos", callback_data="nav:1"),
                InlineKeyboardButton("📊 My Stats", callback_data="stats"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if edit == 1:
            await update.message.edit_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
    except Exception as e:
        log.error(f"Error show_start_menu: {e}")

async def show_statistics(update: Update, context: CallbackContext):
    """
    Stats
    """ 
    def format_flight_time(seconds):
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours} hours\, {minutes} minutes and {seconds} seconds"
        elif minutes > 0:
            return f"{minutes} minutes and {seconds} seconds"
        else:
            return f"{seconds} seconds"
        
    def format_days_count(days):
        years, remainder = divmod(round(days), 365)
        months, days = divmod(remainder, 30)
        
        if years > 0:
            return f"{years} year\(s\) \: {months} month\(s\) \: {days} day\(s\)"
        elif months > 0:
            return f"{months} month\(s\) \: {days} day\(s\)"
        else:
            return f"{days} day\(s\)"
        
    try:
        local_data = await load_local_data(update, context)
        
        days_flown = "`  `*•*` `🛫 You started flying *" + format_days_count(days_since_first_session(local_data)) + " ago*"
        flight_time = "`  `*•*` `⏱️ Total tunnel time\: *" + format_flight_time(total_flight_time(local_data)) + "*"
        text = "\n".join([
            "📊 *Here are some fun stats*\:", 
            days_flown,
            flight_time
        ])
        keyboard = [
            [
                InlineKeyboardButton("← Back", callback_data="home:1")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.edit_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
    except Exception as e:
        log.error(f"Error show_statistics: {e}")

async def navigate_tree(update: Update, context: CallbackContext, direction, day=None, session=None, flight=None, edit=1):
    try:
        local_data = await load_local_data(update, context)
        
        if len(local_data.days) == 0:
            text = "No videos"
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data=f"home:1")]])
        else:
        
            if not day == None:
                if len(local_data.days[day].sessions) == 1:
                    if direction == 1:
                        session = 0
                    else:
                        day = None
            
            text = generate_tree(local_data, day, session, flight) # generating Tree
            
            # Generating buttons (this code is so trash, i want to die)
            if day == None:
                container = local_data.days
                buttons = [InlineKeyboardButton(f"{datetime.fromtimestamp(element.date).strftime('%d.%m.%Y')}", callback_data=f"nav:1:{id}") for id, element in enumerate(container)]
                reply_markup = InlineKeyboardMarkup([[button] for button in buttons] + [[InlineKeyboardButton("← Back", callback_data=f"home:1")]])
            elif session == None:
                container = local_data.days[day].sessions
                buttons = [InlineKeyboardButton(f"Session {id + 1} ({element.time_slot})", callback_data=f"nav:1:{day}:{id}") for id, element in enumerate(container)]
                reply_markup = InlineKeyboardMarkup([[button] for button in buttons] + [[InlineKeyboardButton("← Back", callback_data=f"nav:0")]])
            elif flight == None:
                container = local_data.days[day].sessions[session].flights
                buttons = [InlineKeyboardButton(f"Flight {element.flight_number}", callback_data=f"nav:1:{day}:{session}:{id}") for id, element in enumerate(container)]
                reply_markup = InlineKeyboardMarkup([[button] for button in buttons] + [[InlineKeyboardButton("← Back", callback_data=f"nav:0:{day}")]])
            else:
                container = local_data.days[day].sessions[session].flights[flight].videos
                buttons = [InlineKeyboardButton(f"{element.camera_name}", callback_data=f"video:{day}:{session}:{flight}:{id}") for id, element in enumerate(container)]
                reply_markup = InlineKeyboardMarkup([[button] for button in buttons] + [[InlineKeyboardButton("← Back", callback_data=f"nav:1:{day}:{session}")]])
    
        if edit == 1:
            await update.message.edit_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
            # await update.message.edit_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
            await update.message.delete()
    except Exception as e:
        log.error(f"Error navigate_tree: {e}")

async def open_video(update: Update, context: CallbackContext, day, session, flight, video):
    """
    Open and display a specific video.
    """
    try:
        local_data = await load_local_data(update, context)
        file_id = local_data.days[day].sessions[session].flights[flight].videos[video].file_id
        if not file_id:
            await show_start_menu(update, context, 1)
            
            text = "Video not found"
            await send_closable_message(update, text)
            return
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data=f"nav:1:{day}:{session}:{flight}:0")]])
        await context.bot.send_video(chat_id=update.message.chat_id, video=file_id, reply_markup=reply_markup)
        await update.message.delete()
    except Exception as e:
        log.error(f"open_video: {e}")


# Ifly chat functions
async def ask_for_username(update: Update, context: CallbackContext, restart=0):
    # prompts user with username to upload videos to
    try:
        text = "To upload videos - please send your username"
        await context.bot.edit_message_text(text, IFLY_CHAT_ID, await ifly_menu_message_id(context, restart))
    except Exception as e:
        log.error(f"Error ask_for_username: {e}")
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
                    log.info(f"Found user. Chat_id = {user.chat_id}")
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
        log.error(f"Error ask_for_username: {e}")
        raise

async def start_session(update: Update, context: CallbackContext, confiramtion):
    # upon recieving confirmation - starting session
    # when session ends - updates menu massage to reflect that
    try:
        await update.message.delete()
        log.info(confiramtion)
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
        log.error(f"Error ask_for_username: {e}")
        raise

async def ifly_inline_buttons(update: Update, context: CallbackContext, query):
    # upon recieving confirmation - starting session
    # when session ends - updates menu massage to reflect that
    try:
        parts = query.data.split(':')
        log.info(parts)
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
        log.error(f"Error ask_for_username: {e}")
        raise


def main():
    """
    Main function to start the Telegram bot.
    """
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("clear_data", clear_local_data))
    application.add_handler(CommandHandler("show_data", show_local_data))
    application.add_handler(CommandHandler("create_storage", create_storage_message))
    application.add_handler(MessageHandler(filters.VIDEO, upload_video))
    application.add_handler(MessageHandler(filters.User(user_id=IFLY_CHAT_ID), check_username))
    application.add_handler(MessageHandler(filters.Document.FileExtension("json"), edit_local_data))
    application.add_handler(CallbackQueryHandler(inline_button))

    print("iFLY Videos Bot Online")
    
    application.run_polling()

if __name__ == "__main__":
    main()
