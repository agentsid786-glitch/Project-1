import os
import json
import threading
import time
import telebot
from google import genai
from fastapi import FastAPI
from fastapi.responses import FileResponse
import uvicorn

# ==========================================
# CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PUBLIC_LOG_URL = os.environ.get("PUBLIC_LOG_URL")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Initialize the new 2026 GenAI Client
client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# LOGGING SERVER (FastAPI)
# ==========================================
app = FastAPI()
LOG_FILE = "run.jsonl"

if not os.path.exists(LOG_FILE):
    open(LOG_FILE, "w").close()

@app.get("/run.jsonl")
def get_log():
    return FileResponse(LOG_FILE)

def run_fastapi():
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="error")

# ==========================================
# TELEGRAM BOT LOGIC
# ==========================================
chat_histories = {}

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    user_text = message.text
    
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps({"role": "user", "content": user_text}) + "\n")
        
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
    chat_histories[chat_id].append(f"User: {user_text}")
    history_string = "\n".join(chat_histories[chat_id])
        
    sys_prompt = f"""
    You are a data analyst bot evaluating public datasets.
    Conversation history:
    {history_string}
    
    CRITICAL RULES:
    1. Reply with EXACTLY ONE valid JSON object. No conversational text.
    2. JSON MUST have exactly two keys: "answer" and "log_url".
    3. The "log_url" MUST be exactly: "{PUBLIC_LOG_URL}/run.jsonl"
    4. The "answer" MUST be shaped exactly as the user requested.
    5. DO NOT wrap output in markdown blocks (e.g., no ```json).
    """
    
    try:
        # Use the modern GenAI generation method
        resp = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=sys_prompt
        )
        reply_text = resp.text.strip()
        
        if reply_text.startswith("```json"): reply_text = reply_text[7:]
        if reply_text.startswith("```"): reply_text = reply_text[3:]
        if reply_text.endswith("```"): reply_text = reply_text[:-3]
        reply_text = reply_text.strip()
        
        bot.reply_to(message, reply_text)
        chat_histories[chat_id].append(f"Bot: {reply_text}")
        
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps({"role": "bot", "content": reply_text}) + "\n")
            
    except Exception as e:
        # We added flush=True to force Render to print instantly
        print(f"Error: {e}", flush=True) 
        
        # We are injecting the EXACT error into the Telegram message!
        fallback_json = json.dumps({
            "answer": f"CRASH_REASON: {str(e)}", 
            "log_url": f"{PUBLIC_LOG_URL}/run.jsonl"
        })
        bot.reply_to(message, fallback_json)

if __name__ == "__main__":
    threading.Thread(target=run_fastapi, daemon=True).start()
    print("Bot is polling and API is running...", flush=True)
    bot.polling(none_stop=True)
