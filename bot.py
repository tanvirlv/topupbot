import os
import logging
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters
from steel import Steel
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Configuration from environment variables
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
STEEL_API_KEY = os.environ.get('STEEL_API_KEY')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')  # Your Render URL

# Initialize bot
bot = Bot(token=TELEGRAM_TOKEN)
dispatcher = Dispatcher(bot, None, workers=0, use_context=True)

def fetch_player_name(player_id):
    """
    Fetch player name from Garena using Steel and Playwright
    """
    try:
        # Initialize Steel client
        client = Steel(steel_api_key=STEEL_API_KEY)
        
        # Create a Steel session
        session = client.sessions.create()
        logger.info(f"Steel session created: {session.id}")
        logger.info(f"View session at: {session.session_viewer_url}")
        
        # Start Playwright and connect to Steel
        playwright = sync_playwright().start()
        browser = playwright.chromium.connect_over_cdp(
            f"wss://connect.steel.dev?apiKey={STEEL_API_KEY}&sessionId={session.id}"
        )
        
        # Get the default context and page
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        
        # Navigate to Garena shop
        logger.info("Navigating to Garena shop...")
        page.goto("https://shop.garena.my/?app=100067&channel=202953", wait_until="networkidle")
        
        # Find input field by placeholder and enter player ID
        logger.info(f"Entering player ID: {player_id}")
        input_field = page.get_by_placeholder("Please enter your player ID here")
        input_field.fill(player_id)
        
        # Click the login button using the class selector
        logger.info("Clicking login button...")
        login_button = page.locator('button.shrink-0.rounded-md.bg-primary-red')
        login_button.click()
        
        # Wait for the name field to appear and extract the text
        logger.info("Waiting for player name...")
        name_element = page.locator('div.line-clamp-2.text-sm\\/none.font-bold').first
        name_element.wait_for(timeout=10000)
        
        player_name = name_element.text_content()
        logger.info(f"Player name found: {player_name}")
        
        # Clean up
        browser.close()
        playwright.stop()
        client.sessions.release(session.id)
        logger.info("Session cleaned up")
        
        return player_name
        
    except PlaywrightTimeout:
        logger.error("Timeout: Could not find player name")
        return None
    except Exception as e:
        logger.error(f"Error in fetch_player_name: {str(e)}")
        return None
    finally:
        try:
            browser.close()
            playwright.stop()
            client.sessions.release(session.id)
        except:
            pass

def start(update, context):
    """Send a message when the command /start is issued."""
    update.message.reply_text(
        'Welcome to Garena Player ID Bot! 🎮\n\n'
        'Send me a player ID and I will fetch the player name for you.\n\n'
        'Example: 123456789'
    )

def help_command(update, context):
    """Send a message when the command /help is issued."""
    update.message.reply_text(
        'How to use:\n'
        '1. Send me a player ID (numbers only)\n'
        '2. I will fetch the player name from Garena\n'
        '3. Wait for the result\n\n'
        'Commands:\n'
        '/start - Start the bot\n'
        '/help - Show this help message'
    )

def handle_player_id(update, context):
    """Handle player ID messages"""
    player_id = update.message.text.strip()
    
    # Validate player ID (should be numeric)
    if not player_id.isdigit():
        update.message.reply_text(
            '❌ Invalid player ID. Please send only numbers.\n'
            'Example: 123456789'
        )
        return
    
    # Send processing message
    processing_msg = update.message.reply_text(
        f'🔍 Fetching player name for ID: {player_id}\n'
        'Please wait...'
    )
    
    try:
        # Fetch player name
        player_name = fetch_player_name(player_id)
        
        if player_name:
            # Send success message
            processing_msg.edit_text(
                f'✅ Player Found!\n\n'
                f'Player ID: {player_id}\n'
                f'Player Name: {player_name}'
            )
        else:
            # Send error message
            processing_msg.edit_text(
                f'❌ Could not find player with ID: {player_id}\n\n'
                'Please check the ID and try again.'
            )
    except Exception as e:
        logger.error(f"Error handling player ID: {str(e)}")
        processing_msg.edit_text(
            '❌ An error occurred while fetching player information.\n'
            'Please try again later.'
        )

# Add handlers
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("help", help_command))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_player_id))

@app.route('/')
def index():
    return 'Garena Player ID Bot is running!'

@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    """Handle incoming webhook requests"""
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return 'ok'

def setup_webhook():
    """Setup webhook for Telegram bot"""
    webhook_url = f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}"
    bot.set_webhook(url=webhook_url)
    logger.info(f"Webhook set to: {webhook_url}")

if __name__ == '__main__':
    # Setup webhook
    setup_webhook()
    
    # Run Flask app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
