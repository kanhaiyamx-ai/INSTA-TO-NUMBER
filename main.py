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
    BOT_TOKEN = "8432620857:AAFNkYDZOFnDf0yRlsYDLevkew_TiqVISCo"
    PROXY_URL = "http://yfevdsyx-rotate:fg780yk52y6k@p.webshare.io:80"
    USE_PROXY = True
    REQUEST_TIMEOUT = 30.0
# =============================================

class InstagramEngine:
    def __init__(self):
        self.ua = UserAgent()

    async def fetch_contact_info(self, username: str) -> Dict:
        username = username.lower().replace('@', '').strip()
        result = {"success": False, "email": None, "phone": None, "error": None}
        
        # Fresh client every time to ensure proxy rotation
        async with httpx.AsyncClient(proxy=Config.PROXY_URL, timeout=Config.REQUEST_TIMEOUT, verify=False) as client:
            try:
                logger.info(f"Step 1: Fetching CSRF for @{username}")
                headers = {"User-Agent": self.ua.random}
                init_res = await client.get("https://www.instagram.com/accounts/password/reset/", headers=headers)
                
                csrf = init_res.cookies.get("csrftoken")
                
                await asyncio.sleep(random.uniform(3, 6))

                logger.info(f"Step 2: Sending Reset Request for @{username}")
                post_headers = {
                    "User-Agent": self.ua.random,
                    "Accept": "*/*",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": "https://www.instagram.com/accounts/password/reset/",
                    "X-CSRFToken": csrf if csrf else ""
                }

                payload = {"username_or_email": username, "flow": "recovery"}
                
                response = await client.post(
                    "https://www.instagram.com/api/v1/accounts/send_password_reset_email/",
                    data=payload,
                    headers=post_headers
                )

                if response.status_code == 200:
                    data = response.json()
                    result["email"] = data.get("obfuscated_email")
                    result["phone"] = data.get("obfuscated_phone")
                    result["success"] = True if result["email"] or result["phone"] else False
                    logger.info(f"Success for @{username}")
                else:
                    result["error"] = f"Instagram rejected request (Status: {response.status_code})"
                    logger.warning(f"Failed for @{username}: {response.text[:100]}")

            except Exception as e:
                logger.error(f"Network error: {str(e)}")
                result["error"] = "Proxy timeout or connection issue."
        
        return result

bot = Bot(token=Config.BOT_TOKEN)
dp = Dispatcher()
engine = InstagramEngine()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.reply("🤖 Bot is active! Send a username to check info.")

@dp.message()
async def handle_all(message: Message):
    if not message.text or message.text.startswith('/'): return
    
    msg = await message.answer(f"⏳ Processing `@{message.text}`...")
    res = await engine.fetch_contact_info(message.text)
    
    if res["success"]:
        await msg.edit_text(f"✅ **@{message.text}**\n📧 Email: `{res['email']}`\n📱 Phone: `{res['phone']}`", parse_mode="Markdown")
    else:
        await msg.edit_text(f"❌ Error: {res['error']}")

async def main():
    logger.info("Starting Telegram Bot Polling...")
    # Delete webhook to ensure polling works
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
                  
