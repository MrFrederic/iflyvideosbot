from datetime import datetime

from users import User
from storage_manager import Storage
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaDocument, Chat, InputMediaVideo
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler

class CallbackHandler:  # Handles callbacks and routes
    
    class Callback:
        def __init__(self, route) -> None:
            self.route = route

    # Hard-coded lookup table to store identifiers mapped to full routes with parameters
    route_lookup_table = {
        "01": ("stats", []),
        "02": ("settings", []),
        "03": ("home", []),
        "04": ("library", ["date"]),
        "05": ("video", ["id"]),
        "06": ("video_settings", ["id"]),
        "07": ("global_home", ["user"]),
        "08": ("global_settings", ["user"]),
        "09": ("global_login", ["user"]),
    }

    def __compress_date(num):
        return str(int(num) // 86400)

    def __uncompress_date(compressed_str):
        return int(compressed_str) * 86400 + 1
    
    @classmethod
    def compress_route(cls, route: str, *params) -> str:
        for identifier, (stored_route, params_names) in cls.route_lookup_table.items():
            if route == stored_route and len(params) == len(params_names):
                params = [
                    cls.__compress_date(param) if param_name == 'date' else (
                            '-' if param is None else str(param)
                        )
                    for param_name, param in zip(params_names, params)
                ]
                join_str = [str(identifier)]
                if params: join_str.append(':'.join(params))   
                comp_route = '?'.join(join_str)
                
                if len(comp_route) <= 60:  # Check that the length of the compressed route is within the limit
                    return comp_route
        
        raise ValueError("Route and parameters not found in the lookup table or parameters are too long.")

    @classmethod
    def decompress_route(cls, comp_route: str):
        # Handle case where there are no parameters
        if '?' in comp_route:
            identifier, params_str = comp_route.split('?')
            params_values = params_str.split(':') if params_str else []
        else:
            identifier = comp_route
            params_values = []
        
        if identifier not in cls.route_lookup_table:
            raise ValueError("Identifier not found in the lookup table.")
        
        route, params_names = cls.route_lookup_table[identifier]
        
        if len(params_names) != len(params_values):
            raise ValueError("Mismatch between the number of parameters and the lookup table.")
        
        callback = cls.Callback(route)
        params_values = [
            cls.__uncompress_date(param_value) if param_name == 'date' else (
                    None if param_value == "None" else param_value
                )
                for param_name, param_value in zip(params_names, params_values)
            ]
        for param_name, param_value in zip(params_names, params_values):
            setattr(callback, param_name, param_value)
        
        return callback  # Returning the callback object

class Chat:
    def __init__(self, user: User, ) -> None:
        self.id = user.id
        self.user = user

    def update_state():
        pass

class Inteface:
    # methods to for generating "screens"
    @classmethod
    def home(cls):
        text = """Welcome to Ifly Videos bot!\n\nHere you can store and manage videos of your flights"""
        reply_markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎥 Browse Videos", callback_data=CallbackHandler.compress_route("library")),
            ],
            [
                InlineKeyboardButton("📊 My Stats", callback_data=CallbackHandler.compress_route("stats")),
                InlineKeyboardButton("⚙️ Settings", callback_data=CallbackHandler.compress_route("settings")),
            ]
        ])

    @classmethod
    def video(cls, id, storage: Storage):
        # helper functions
        def transform_timestamp(timestamp):
            # Convert the timestamp to a datetime object
            dt_object = datetime.fromtimestamp(timestamp)
            # Format the datetime object to the desired format
            formatted_time = dt_object.strftime('%d.%m.%Y %H:%M')
            return formatted_time

        video = storage.video(id)
        flight = storage.flight(video.id)
        flight_date = transform_timestamp(flight.datetime)
        flyers = storage.list_flights_users(flight)
        
        
        text = f"""📅 Date: {flight_date}\n🪂 Flyers: {", ".join([flyer.username for flyer in flyers])}\n⌛️ Duration: {flight.length // 60}:{flight.length % 60} min ({flight.length // 60} sec)"""
        reply_markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎥 Browse Videos", callback_data=CallbackHandler.compress_route("library")),
            ],
            [
                InlineKeyboardButton("📊 My Stats", callback_data=CallbackHandler.compress_route("stats")),
                InlineKeyboardButton("⚙️ Settings", callback_data=CallbackHandler.compress_route("settings")),
            ]
        ])
        media = InputMediaVideo(video.telegram_id)



#        "01": ("stats", []),
#        "02": ("settings", []),
#        "03": ("home", []),
#        "04": ("library", ["date"]),
#        "05": ("video", ["id"]),
#        "06": ("global_home", ["user"]),
#        "07": ("global_settings", ["user"]),
#        "08": ("global_login", ["user"]),