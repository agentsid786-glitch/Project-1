import os
import json
import threading
import time
import telebot
import google.generativeai as genai
from fastapi import FastAPI
from fastapi.responses import FileResponse
import uvicorn

# ==========================================
# CONFIGURATION
# ==========================================
# These safely pull from Colab without exposing your keys on GitHub
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PUBLIC_LOG_URL = os.environ.get("PUBLIC_LOG_URL")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
genai.configure(api_key=GEMINI_API_KEY)

# Using Gemini 1.5 Flash (Fast and accurate for data tasks)
model = genai.GenerativeModel('gemini-1.5-flash')

# ==========================================
# LOGGING SERVER (FastAPI)
# ==========================================
app = FastAPI()
LOG_FILE = "run.jsonl"

# Ensure log file exists
if not os.path.exists(LOG_FILE):
    open(LOG_FILE, "w").close()

@app.get("/run.jsonl")
def get_log():
    # The auto-grader will download this file
    return FileResponse(LOG_FILE)

def run_fastapi():
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="error")

# ==========================================
# TELEGRAM BOT LOGIC
# ==========================================
chat_histories = {}

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    user_text = message.text
    
    # 1. Log incoming user message
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps({"role": "user", "content": user_text}) + "\n")
        
    # 2. Update multi-turn history
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
    chat_histories[chat_id].append(f"User: {user_text}")
    history_string = "\n".join(chat_histories[chat_id])
        
    # 3. AI Prompt Instructions
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
        # 4. Generate Answer
        resp = model.generate_content(sys_prompt)
        reply_text = resp.text.strip()
        
        # Clean formatting just in case
        if reply_text.startswith("```json"): reply_text = reply_text[7:]
        if reply_text.startswith("```"): reply_text = reply_text[3:]
        if reply_text.endswith("```"): reply_text = reply_text[:-3]
        reply_text = reply_text.strip()
        
        # 5. Send to Telegram
        bot.reply_to(message, reply_text)
        chat_histories[chat_id].append(f"Bot: {reply_text}")
        
        # 6. Log bot's response
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps({"role": "bot", "content": reply_text}) + "\n")
            
    except Exception as e:
        fallback_json = json.dumps({
            "answer": "error", 
            "log_url": f"{PUBLIC_LOG_URL}/run.jsonl"
        })
        bot.reply_to(message, fallback_json)

if __name__ == "__main__":
    # Start log-serving API in background
    threading.Thread(target=run_fastapi, daemon=True).start()
    print("Bot is polling and API is running...")
    # Start listening to Telegram
    bot.polling(none_stop=True)
