#!/usr/bin/env python3
"""
Instagram Contact Info Bot
Educational/Research Use Only
Author: Telegram Bot Specialist
"""

import asyncio
import random
import re
import json
import time
from datetime import datetime
from typing import Optional, Dict, Tuple
import logging

# Third-party imports
import aiogram
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from loguru import logger
import cloudscraper
from fake_useragent import UserAgent
import httpx
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ========== CONFIGURATION ==========
class Config:
    # Telegram Bot Token (from @BotFather)
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    
    # Proxy Configuration
    PROXY_URL = os.getenv("PROXY_URL", "http://yfevdsyx-rotate:fg780yk52y6k@p.webshare.io:80")
    USE_PROXY = True
    PROXY_ROTATION_INTERVAL = 3  # Rotate after every 3 requests
    
    # Instagram Settings
    INSTAGRAM_FORGOT_PASSWORD_URL = "https://www.instagram.com/accounts/password/reset/"
    INSTAGRAM_LOGIN_URL = "https://www.instagram.com/accounts/login/"
    
    # Request Settings
    MIN_DELAY = 5  # seconds
    MAX_DELAY = 15  # seconds
    MAX_RETRIES = 2
    TIMEOUT = 30
    
    # Bot Behavior
    MAX_REQUESTS_PER_MINUTE = 10
    WARNING_MESSAGE = (
        "⚠️ **Disclaimer:** This bot is for educational and research purposes only.\n"
        "Do not abuse, spam, or use for malicious activities.\n"
        "Respect Instagram's Terms of Service and rate limits."
    )

# ========== PROXY MANAGER ==========
class ProxyManager:
    """Manages rotating residential proxies"""
    
    def __init__(self, proxy_url: str):
        self.proxy_url = proxy_url
        self.request_count = 0
        self.rotation_interval = Config.PROXY_ROTATION_INTERVAL
        self.current_proxy = None
        self.proxies_pool = self._generate_proxy_variants()
        
    def _generate_proxy_variants(self) -> list:
        """Generate multiple proxy variants from base URL"""
        variants = []
        base = self.proxy_url
        
        # Add variations with different session IDs
        for i in range(5):
            variant = base.replace("-rotate:", f"-rotate-session{i}:")
            variants.append(variant)
        
        variants.append(base)  # Keep original
        return variants
    
    def get_proxy(self) -> Optional[Dict]:
        """Get next proxy with rotation logic"""
        self.request_count += 1
        
        # Rotate proxy based on interval
        if self.request_count % self.rotation_interval == 0:
            self.current_proxy = random.choice(self.proxies_pool)
            logger.info(f"Rotating to new proxy: {self.current_proxy[:50]}...")
        
        if not self.current_proxy:
            self.current_proxy = random.choice(self.proxies_pool)
        
        if Config.USE_PROXY:
            return {
                "http": self.current_proxy,
                "https": self.current_proxy
            }
        return None
    
    def get_cloudscraper_proxy(self) -> Optional[str]:
        """Get proxy in format for cloudscraper"""
        if Config.USE_PROXY and self.current_proxy:
            return self.current_proxy
        return None

# ========== INSTAGRAM SCRAPER ==========
class InstagramScraper:
    """Handles Instagram forgot password flow with anti-detection measures"""
    
    def __init__(self):
        self.proxy_manager = ProxyManager(Config.PROXY_URL)
        self.ua = UserAgent()
        self.session = None
        self.csrf_token = None
        self.request_history = []
        
    def _get_random_delay(self) -> float:
        """Get random delay between requests"""
        return random.uniform(Config.MIN_DELAY, Config.MAX_DELAY)
    
    def _get_headers(self) -> Dict:
        """Generate random headers for each request"""
        headers = {
            "User-Agent": self.ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
        return headers
    
    def _extract_csrf_token(self, html: str) -> Optional[str]:
        """Extract CSRF token from Instagram page"""
        patterns = [
            r'"csrf_token":"([^"]+)"',
            r'name="csrfmiddlewaretoken"\s+value="([^"]+)"',
            r'"token":"([^"]+)"'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return match.group(1)
        
        # Try BeautifulSoup extraction
        soup = BeautifulSoup(html, 'html.parser')
        meta_token = soup.find('meta', {'name': 'csrf-token'})
        if meta_token and meta_token.get('content'):
            return meta_token['content']
        
        input_token = soup.find('input', {'name': 'csrfmiddlewaretoken'})
        if input_token and input_token.get('value'):
            return input_token['value']
        
        return None
    
    def _extract_contact_info(self, html: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract masked contact info from Instagram's password reset page
        Returns: (masked_email, masked_phone)
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # Patterns Instagram uses for masked info
        masked_email = None
        masked_phone = None
        
        # Look for email patterns
        email_patterns = [
            r'([a-zA-Z0-9._%+-])\*\*\*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            r'([a-zA-Z0-9])\*\*\*@gmail\.com',
            r'([a-zA-Z0-9])\*\*\*@yahoo\.com',
            r'([a-zA-Z0-9])\*\*\*@hotmail\.com',
            r'([a-zA-Z0-9])\*\*\*@outlook\.com',
            r'data-email="([^"]+)"',
            r'"email":"([^"]+)"'
        ]
        
        # Look for phone patterns
        phone_patterns = [
            r'\*\*\*\*\*\*(\d{2})',  # ******12
            r'\*\*\*\*\*(\d{2})',    # *****12
            r'(\d{2})\s*\(last\s+2\s+digits\)',
            r'"phone":"([^"]+)"',
            r'data-phone="([^"]+)"'
        ]
        
        html_text = str(soup)
        
        # Check for email
        for pattern in email_patterns:
            match = re.search(pattern, html_text, re.IGNORECASE)
            if match:
                masked_email = match.group(0)
                break
        
        # Check for phone
        for pattern in phone_patterns:
            match = re.search(pattern, html_text)
            if match:
                masked_phone = match.group(0)
                break
        
        # Additional HTML element search
        if not masked_email:
            email_elements = soup.find_all(['span', 'div', 'p'], 
                                         string=re.compile(r'\*.*@.*\..*'))
            if email_elements:
                masked_email = email_elements[0].get_text(strip=True)
        
        if not masked_phone:
            phone_elements = soup.find_all(['span', 'div', 'p'], 
                                         string=re.compile(r'\*.*\d{2}'))
            if phone_elements:
                masked_phone = phone_elements[0].get_text(strip=True)
        
        return masked_email, masked_phone
    
    def check_instagram_user(self, username: str) -> Dict:
        """
        Main function to check Instagram user's contact info
        Returns dict with status and data
        """
        result = {
            "success": False,
            "username": username,
            "masked_email": None,
            "masked_phone": None,
            "error": None,
            "response_code": None,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # Clean username
            username = username.replace('@', '').strip()
            
            if not username:
                result["error"] = "Invalid username"
                return result
            
            logger.info(f"Checking Instagram user: @{username}")
            
            # Create new session for each request
            scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True,
                    'mobile': False
                },
                delay=10
            )
            
            # Get proxy for this request
            proxy = self.proxy_manager.get_cloudscraper_proxy()
            if proxy and Config.USE_PROXY:
                scraper.proxies = {"http": proxy, "https": proxy}
            
            # Initial request to get CSRF token
            headers = self._get_headers()
            logger.debug(f"Using headers: {headers['User-Agent'][:50]}...")
            
            # Initial delay
            delay = self._get_random_delay()
            logger.debug(f"Initial delay: {delay:.2f} seconds")
            time.sleep(delay)
            
            # Get login page for CSRF token
            try:
                response = scraper.get(
                    Config.INSTAGRAM_LOGIN_URL,
                    headers=headers,
                    timeout=Config.TIMEOUT
                )
                result["response_code"] = response.status_code
                
                if response.status_code != 200:
                    logger.warning(f"Initial request failed: {response.status_code}")
                    if response.status_code == 429:
                        result["error"] = "Rate limited by Instagram"
                        return result
                    elif response.status_code == 403:
                        result["error"] = "Cloudflare block detected"
                        return result
                
                self.csrf_token = self._extract_csrf_token(response.text)
                logger.debug(f"CSRF Token extracted: {self.csrf_token[:20] if self.csrf_token else 'None'}")
                
            except Exception as e:
                logger.error(f"Initial request error: {str(e)}")
                result["error"] = f"Network error: {str(e)}"
                return result
            
            # Second delay before password reset request
            delay = self._get_random_delay()
            logger.debug(f"Second delay: {delay:.2f} seconds")
            time.sleep(delay)
            
            # Prepare password reset request
            reset_url = Config.INSTAGRAM_FORGOT_PASSWORD_URL
            headers.update({
                "Referer": Config.INSTAGRAM_LOGIN_URL,
                "Origin": "https://www.instagram.com",
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRFToken": self.csrf_token if self.csrf_token else "",
                "X-Instagram-AJAX": "1",
                "X-Requested-With": "XMLHttpRequest"
            })
            
            # Make password reset request
            try:
                reset_data = {
                    "username_or_email": username,
                    "csrfmiddlewaretoken": self.csrf_token if self.csrf_token else ""
                }
                
                response = scraper.post(
                    reset_url,
                    data=reset_data,
                    headers=headers,
                    timeout=Config.TIMEOUT
                )
                
                result["response_code"] = response.status_code
                logger.debug(f"Reset request status: {response.status_code}")
                
                # Handle different responses
                if response.status_code == 200:
                    html_content = response.text
                    
                    # Check for various Instagram responses
                    if "challenge_required" in html_content.lower():
                        result["error"] = "Challenge required (suspicious activity)"
                    elif "rate limited" in html_content.lower() or "too many requests" in html_content.lower():
                        result["error"] = "Rate limited by Instagram"
                    elif "sorry, this page isn't available" in html_content.lower():
                        result["error"] = "Account not found or private"
                    elif "enter the code we sent" in html_content.lower() or "send code" in html_content.lower():
                        # This is what we want - password reset page showing contact info
                        masked_email, masked_phone = self._extract_contact_info(html_content)
                        
                        if masked_email or masked_phone:
                            result["success"] = True
                            result["masked_email"] = masked_email
                            result["masked_phone"] = masked_phone
                            logger.info(f"Success for @{username}: Email={masked_email}, Phone={masked_phone}")
                        else:
                            result["error"] = "No phone/email visible"
                            logger.info(f"No contact info found for @{username}")
                    else:
                        # Try to extract anyway
                        masked_email, masked_phone = self._extract_contact_info(html_content)
                        if masked_email or masked_phone:
                            result["success"] = True
                            result["masked_email"] = masked_email
                            result["masked_phone"] = masked_phone
                        else:
                            result["error"] = "Unexpected response format"
                
                elif response.status_code == 429:
                    result["error"] = "Rate limited"
                elif response.status_code == 404:
                    result["error"] = "Account not found"
                elif response.status_code == 403:
                    result["error"] = "Access denied (Cloudflare)"
                else:
                    result["error"] = f"HTTP Error: {response.status_code}"
                
            except cloudscraper.exceptions.CloudflareChallengeError:
                result["error"] = "Cloudflare challenge failed"
                logger.error("Cloudflare challenge detected and failed")
            except Exception as e:
                logger.error(f"Reset request error: {str(e)}")
                result["error"] = f"Request failed: {str(e)}"
            
            # Clean up
            scraper.close()
            
        except Exception as e:
            logger.error(f"Unexpected error in check_instagram_user: {str(e)}")
            result["error"] = f"System error: {str(e)}"
        
        return result

# ========== TELEGRAM BOT ==========
class InstagramBot:
    def __init__(self):
        self.bot = None
        self.dp = None
        self.scraper = InstagramScraper()
        self.user_requests = {}  # Track user request frequency
        
    async def start_command(self, message: Message):
        """Handle /start command"""
        welcome_text = (
            "👋 *Welcome to Instagram Contact Info Bot*\n\n"
            "Send me an Instagram username (with or without @) and I'll try to find "
            "masked contact information from the password reset page.\n\n"
            "*Example:* `instagram` or `@username`\n\n"
            f"{Config.WARNING_MESSAGE}\n\n"
            "*Commands:*\n"
            "/start - Show this message\n"
            "/help - Show help information\n"
            "/status - Check bot status\n"
            "/limit - Show usage limits"
        )
        
        await message.answer(
            welcome_text,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    
    async def help_command(self, message: Message):
        """Handle /help command"""
        help_text = (
            "❓ *How to use this bot:*\n\n"
            "1. Send any Instagram username (e.g., `instagram` or `@username`)\n"
            "2. Bot will attempt to access the password reset page\n"
            "3. Returns:\n"
            "   • Masked email (e.g., a***@gmail.com)\n"
            "   • Last 2 phone digits (e.g., ******12)\n"
            "   • Or error message\n\n"
            "*Limitations:*\n"
            "• Rate limited to 10 requests per minute\n"
            "• May not work for private accounts\n"
            "• Instagram may block frequent requests\n\n"
            f"{Config.WARNING_MESSAGE}"
        )
        
        await message.answer(
            help_text,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    
    async def status_command(self, message: Message):
        """Handle /status command"""
        status_text = (
            "✅ *Bot Status:* Online\n"
            "📊 *Proxy:* Active\n"
            "🛡️ *Anti-detection:* Enabled\n"
            "⏱️ *Request Delay:* 5-15 seconds\n"
            "🔄 *Proxy Rotation:* Every 3 requests\n\n"
            "*Current Usage:*\n"
            f"Total users tracked: {len(self.user_requests)}\n"
            "Last reset: Ongoing\n\n"
            "Bot is functioning normally."
        )
        
        await message.answer(status_text, parse_mode="Markdown")
    
    async def limit_command(self, message: Message):
        """Handle /limit command"""
        user_id = message.from_user.id
        current_time = time.time()
        
        # Clean old requests
        if user_id in self.user_requests:
            self.user_requests[user_id] = [
                req_time for req_time in self.user_requests[user_id]
                if current_time - req_time < 60  # Keep only last minute
            ]
        
        request_count = len(self.user_requests.get(user_id, []))
        remaining = max(0, Config.MAX_REQUESTS_PER_MINUTE - request_count)
        
        limit_text = (
            f"📊 *Your Usage Limits:*\n\n"
            f"• Requests this minute: {request_count}\n"
            f"• Remaining requests: {remaining}\n"
            f"• Limit resets in: 60 seconds\n\n"
            "*Total limit:* 10 requests per minute\n\n"
            "Please wait if you hit the limit to avoid blocks."
        )
        
        await message.answer(limit_text, parse_mode="Markdown")
    
    def _check_rate_limit(self, user_id: int) -> bool:
        """Check if user has exceeded rate limit"""
        current_time = time.time()
        
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []
        
        # Remove requests older than 1 minute
        self.user_requests[user_id] = [
            req_time for req_time in self.user_requests[user_id]
            if current_time - req_time < 60
        ]
        
        # Check if under limit
        if len(self.user_requests[user_id]) >= Config.MAX_REQUESTS_PER_MINUTE:
            return False
        
        # Add current request
        self.user_requests[user_id].append(current_time)
        return True
    
    async def handle_username(self, message: Message):
        """Main handler for Instagram username requests"""
        user_id = message.from_user.id
        username = message.text.strip()
        
        # Check rate limit
        if not self._check_rate_limit(user_id):
            await message.answer(
                "⏳ *Rate Limit Exceeded*\n\n"
                "You've made too many requests in the last minute.\n"
                "Please wait 60 seconds before trying again.\n\n"
                "Use /limit to check your current usage.",
                parse_mode="Markdown"
            )
            return
        
        # Remove @ symbol if present
        if username.startswith('@'):
            username = username[1:]
        
        # Validate username
        if not username or len(username) > 30:
            await message.answer(
                "❌ *Invalid Username*\n\n"
                "Please send a valid Instagram username.\n"
                "Example: `instagram` or `@username`",
                parse_mode="Markdown"
            )
            return
        
        # Send processing message
        processing_msg = await message.answer(
            f"🔍 *Processing:* @{username}\n"
            "This may take 10-20 seconds...",
            parse_mode="Markdown"
        )
        
        try:
            # Check Instagram user
            result = self.scraper.check_instagram_user(username)
            
            # Format response based on result
            if result["success"]:
                response_text = f"✅ *Results for @{username}:*\n\n"
                
                if result["masked_email"]:
                    response_text += f"📧 *Email:* `{result['masked_email']}`\n"
                
                if result["masked_phone"]:
                    response_text += f"📱 *Phone:* `{result['masked_phone']}`\n"
                
                if not result["masked_email"] and not result["masked_phone"]:
                    response_text += "No contact information visible.\n"
                
                response_text += f"\n⏰ *Checked at:* {result['timestamp'][11:19]}"
                
            else:
                error_msg = result["error"] or "Unknown error"
                
                # User-friendly error messages
                if "rate limit" in error_msg.lower():
                    error_display = "⏳ Instagram rate limited this request"
                elif "account not found" in error_msg.lower():
                    error_display = "❓ Account not found or is private"
                elif "no phone/email" in error_msg.lower():
                    error_display = "🔒 No contact information visible"
                elif "challenge" in error_msg.lower():
                    error_display = "🛡️ Instagram detected unusual activity"
                elif "cloudflare" in error_msg.lower():
                    error_display = "🛡️ Blocked by Cloudflare protection"
                else:
                    error_display = f"⚠️ Error: {error_msg}"
                
                response_text = (
                    f"❌ *Could not retrieve info for @{username}:*\n\n"
                    f"{error_display}\n\n"
                    "Possible reasons:\n"
                    "• Account is private\n"
                    "• No contact info linked\n"
                    "• Instagram anti-bot detection\n"
                    "• Temporary block\n\n"
                    f"*Response code:* {result['response_code'] or 'N/A'}"
                )
            
            # Add warning footer
            response_text += f"\n\n{Config.WARNING_MESSAGE}"
            
            await processing_msg.edit_text(
                response_text,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Error handling username {username}: {str(e)}")
            
            await processing_msg.edit_text(
                f"❌ *System Error*\n\n"
                f"An error occurred while processing @{username}:\n"
                f"`{str(e)[:100]}`\n\n"
                "Please try again later or contact support.",
                parse_mode="Markdown"
            )
    
    async def run(self):
        """Start the bot"""
        if not Config.BOT_TOKEN:
            logger.error("BOT_TOKEN not set in environment variables!")
            raise ValueError("Please set BOT_TOKEN environment variable")
        
        # Initialize bot
        self.bot = Bot(token=Config.BOT_TOKEN)
        self.dp = Dispatcher()
        
        # Register handlers
        self.dp.message.register(self.start_command, Command("start"))
        self.dp.message.register(self.help_command, Command("help"))
        self.dp.message.register(self.status_command, Command("status"))
        self.dp.message.register(self.limit_command, Command("limit"))
        self.dp.message.register(self.handle_username)
        
        logger.info("Starting Instagram Contact Info Bot...")
        logger.info(f"Proxy enabled: {Config.USE_PROXY}")
        logger.info(f"Max requests per minute: {Config.MAX_REQUESTS_PER_MINUTE}")
        
        # Start polling
        await self.dp.start_polling(self.bot)

# ========== MAIN ENTRY POINT ==========
async def main():
    """Main function to run the bot"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize and run bot
    bot = InstagramBot()
    
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
