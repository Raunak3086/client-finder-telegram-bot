import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import asyncio

# Import functions from our agent script
from client_finder_agent import find_potential_clients, generate_pdf

# --- Dummy Web Server for Render ---
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running!")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

def keep_alive():
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    print(f"Dummy web server started on port {port}")
# -----------------------------------

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# Define states for the conversation
CITY, BUSINESS_TYPE = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation and asks for the city."""
    await update.message.reply_text(
        "👋 Welcome to the Web Dev Lead Generator Bot!\n\n"
        "I can help you find local businesses that don't have a website but have good Google reviews.\n\n"
        "To get started, please tell me the **City** you want to search in (e.g., Prayagraj, New York, London):",
        parse_mode='Markdown'
    )
    return CITY

async def ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the city and asks for the business type."""
    city = update.message.text.strip()
    
    if city.lower() in ['hi', 'hello', 'hey', 'start', '/start']:
        await update.message.reply_text("Please enter a valid city name (e.g., New York, London).")
        return CITY
        
    context.user_data['city'] = city
    
    await update.message.reply_text(
        f"Great! I will search in **{city}**.\n\n"
        "Now, what **type of business** are you looking for? (e.g., clinic, plumber, restaurant, dentist):",
        parse_mode='Markdown'
    )
    return BUSINESS_TYPE

async def run_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Runs the lead generator and returns the PDF."""
    business_type = update.message.text
    city = context.user_data['city']
    
    await update.message.reply_text(
        f"🔍 Searching for `{business_type}` in `{city}`...\n\n"
        "This usually takes 1-2 minutes. I'm checking Google Maps and searching for emails. Please wait! ⏳",
        parse_mode='Markdown'
    )
    
    # Run the lead generation process (blocks execution, but it's fine for a simple bot)
    try:
        leads = find_potential_clients(GOOGLE_MAPS_API_KEY, city, business_type=business_type, min_reviews=20)
        
        # Generate the PDF
        pdf_filename = generate_pdf(leads, f"{business_type.capitalize()}s in {city.capitalize()}")
        
        if not leads:
            await update.message.reply_text("❌ No businesses found matching your criteria (no website + 20+ reviews). Try another city or type.")
        else:
            await update.message.reply_text(f"✅ Found {len(leads)} leads! Sending the PDF now...")
            
            # Send the document
            with open(pdf_filename, 'rb') as doc:
                await update.message.reply_document(document=doc, filename=pdf_filename)
                
            # Cleanup the file locally
            if os.path.exists(pdf_filename):
                os.remove(pdf_filename)
                
    except Exception as e:
        await update.message.reply_text(f"⚠️ An error occurred while generating leads: {e}")
        
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    await update.message.reply_text("Search cancelled. Type /start to begin a new search.")
    return ConversationHandler.END

def main() -> None:
    """Run the bot."""
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found in .env file.")
        return
        
    if not GOOGLE_MAPS_API_KEY:
        print("Error: GOOGLE_MAPS_API_KEY not found in .env file.")
        return

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add conversation handler with the states CITY and BUSINESS_TYPE
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, start)
        ],
        states={
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_city)],
            BUSINESS_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, run_search)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)

    # Start the dummy web server to satisfy Render's port binding requirement
    keep_alive()

    # Run the bot until the user presses Ctrl-C
    print("Bot is up and running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
