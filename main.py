import asyncio
import random
import time
from typing import Dict

import httpx
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from loguru import logger
from fake_useragent import UserAgent

# ========== HARDCODED CONFIGURATION ==========
class Config:
    # Your Telegram Bot Token
    BOT_TOKEN = "8432620857:AAFNkYDZOFnDf0yRlsYDLevkew_TiqVISCo"
    
    # Your Proxy (Converted to standard URI format)
    PROXY_URL = "http://yfevdsyx-rotate:fg780yk52y6k@p.webshare.io:80"
    
    USE_PROXY = True
    REQUEST_TIMEOUT = 30.0
    MIN_DELAY = 4
    MAX_DELAY = 8
# =============================================

class InstagramEngine:
    def __init__(self):
        self.ua = UserAgent()

    def _get_headers(self) -> Dict:
        return {
            "User-Agent": self.ua.random,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.instagram.com/accounts/password/reset/",
            "X-IG-App-ID": "936619743392459",
            "Connection": "keep-alive",
        }

    async def fetch_contact_info(self, username: str) -> Dict:
        username = username.lower().replace('@', '').strip()
        result = {"success": False, "email": None, "phone": None, "error": None}
        
        # FIX: Changed 'proxies' to 'proxy' to support httpx 0.28.0+
        proxy_config = Config.PROXY_URL if Config.USE_PROXY else None
        
        async with httpx.AsyncClient(proxy=proxy_config, timeout=Config.REQUEST_TIMEOUT, verify=False) as client:
            try:
                logger.info(f"Connecting to Instagram for @{username}...")
                
                # Step 1: Initial request to get cookies/session
                init_res = await client.get("https://www.instagram.com/accounts/password/reset/")
                csrf = init_res.cookies.get("csrftoken")
                
                # Human-like delay
                await asyncio.sleep(random.uniform(Config.MIN_DELAY, Config.MAX_DELAY))

                # Step 2: Post to the password reset API
                headers = self._get_headers()
                if csrf:
                    headers["X-CSRFToken"] = csrf

                payload = {"username_or_email": username, "flow": "recovery"}
                
                response = await client.post(
                    "https://www.instagram.com/api/v1/accounts/send_password_reset_email/",
                    data=payload,
                    headers=headers
                )

                if response.status_code == 200:
                    data = response.json()
                    result["email"] = data.get("obfuscated_email")
                    result["phone"] = data.get("obfuscated_phone")
                    result["success"] = True if result["email"] or result["phone"] else False
                    if not result["success"]:
                        result["error"] = "No contact info linked to this account."
                elif response.status_code == 429:
                    result["error"] = "Instagram Rate Limit. Please try again later."
                elif response.status_code == 404:
                    result["error"] = "Account not found."
                else:
                    result["error"] = f"Request blocked (HTTP {response.status_code})"

            except Exception as e:
                logger.error(f"Engine Error: {e}")
                result["error"] = "Proxy connection or timeout error."
        
        return result

# ========== BOT HANDLERS ==========
bot = Bot(token=Config.BOT_TOKEN)
dp = Dispatcher()
engine = InstagramEngine()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.reply("👋 Send me an Instagram username (e.g., `cristiano`) to see masked contact info!")

@dp.message()
async def handle_all(message: Message):
    if not message.text or message.text.startswith('/'): return
    
    status_msg = await message.answer(f"🔍 Checking `@{message.text}`...")
    
    try:
        data = await engine.fetch_contact_info(message.text)
        
        if data["success"]:
            text = (
                f"✅ **Results for @{message.text}:**\n\n"
                f"📧 **Email:** `{data['email'] or 'Not set'}`\n"
                f"📱 **Phone:** `{data['phone'] or 'Not set'}`"
            )
        else:
            text = f"❌ **Error:** {data['error']}"
            
        await status_msg.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Bot Handler Error: {e}")
        await status_msg.edit_text("❌ A system error occurred. Please try again.")

async def main():
    logger.info("Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
                  
