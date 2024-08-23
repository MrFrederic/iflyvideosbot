from users import User
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaDocument, Chat
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler

class CallbackHandler:
    pass

class Chat:
    def __init__(self, user: User, ) -> None:
        self.id = user.id
        self.user = user

class Inteface:
    pass

    @classmethod
    def main_menu(cls):
        text = """Welcome to Ifly Videos bot!\n\nHere you can store and manage videos of your flights"""
        reply_markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎥 Browse Videos", callback_data=None),
                InlineKeyboardButton("📊 My Stats", callback_data=None),
            ]
        ])
