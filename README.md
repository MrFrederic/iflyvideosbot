# iflyvideosbot
This is my little Telegram bot for managing videos I've got from my bodyflight sessions.

## Key Features
This bot can accept videos from user, parse their filenames and sore in an organised way. All videos are stored on Telegram's servers.
You can also set up dedicated accout that bott will handle as a upload-only account. You will need to authentificate yourself and then you will be able to upload videos directly to your own account.

## Deploying
1. Run `pip install -r requirements.txt` to install dependencies
2. Create a ".env" with following context:

``BOT_TOKEN=000000000:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA # Token you'v got from t.me/BotFather

IFLY_CHAT_ID=1234567890 # ID for sender-only user``

4. Run `python main.py`
