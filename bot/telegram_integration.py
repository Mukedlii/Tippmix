"""
bot/telegram_integration.py

Integration layer: Poisson engine → Telegram messages (VIP + FREE)

Workflow:
1. Generate tips from Poisson engine
2. Deduplicate + filter PRO leagues
3. Apply rate limits
4. Format for Telegram
5. Send to channels
"""

import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from bot.deduplication import deduplicate_tips, filter_by_league_tier, apply_rate_limit
from bot.roi_display import inject_roi_into_vip_message, has_completed_matches_today
from bot.telegram_pro_format import (
    format_vip_message,
    format_free_message,
    validate_tips_for_vip,
    validate_tips_for_free,
    create_inline_buttons_pro,
)

log = logging.getLogger(__name__)


class TelegramMessageBuilder:
    """Build and send professional Telegram messages."""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("TIPPMIX_DB_PATH", "data/tippmix.db")
        self.vip_chat_id = os.getenv("TIPPMIX_VIP_CHAT_ID")
        self.free_chat_id = os.getenv("TIPPMIX_FREE_CHAT_ID")
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    def process_tips(
        self,
        all_tips: List[Dict[str, Any]],
        tier: str = "VIP"
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Process raw tips for Telegram message.
        
        Args:
            all_tips: Raw tips from Poisson engine
            tier: "VIP" or "FREE"
        
        Returns:
            (processed_tips, removed_count)
        """
        
        original_count = len(all_tips)
        
        # Stage 1: Deduplicate (1 per match)
        deduped = deduplicate_tips(all_tips)
        log.info(f"[DEDUP] {original_count} → {len(deduped)} tips")
        
        # Stage 2: Filter by league tier
        filtered = filter_by_league_tier(deduped, tier=tier)
        log.info(f"[LEAGUE] {len(deduped)} → {len(filtered)} ({tier})")
        
        # Stage 3: Apply rate limit
        if tier == "VIP":
            max_tips = int(os.getenv("TIPPMIX_MAX_TIPS_VIP", "12"))
        else:
            max_tips = int(os.getenv("TIPPMIX_MAX_TIPS_FREE", "3"))
        
        limited = apply_rate_limit(filtered, max_per_run=max_tips)
        log.info(f"[LIMIT] {len(filtered)} → {len(limited)} (max={max_tips})")
        
        removed = original_count - len(limited)
        
        return limited, removed
    
    def build_vip_message(
        self,
        tips: List[Dict[str, Any]],
        date_str: str = ""
    ) -> Optional[str]:
        """
        Build VIP message if minimum 6 PRO tips available.
        
        Args:
            tips: Processed tips
            date_str: Date string (YYYY.MM.DD.)
        
        Returns:
            Formatted message or None if not enough tips
        """
        
        # Validate: 6+ PRO tips with odds
        if not validate_tips_for_vip(tips):
            log.warning(f"[VIP] Not enough PRO tips: {len(tips)} < 6 required")
            return None
        
        # Format base message
        message = format_vip_message(tips, date_str=date_str)
        
        # Inject ROI if available
        message = inject_roi_into_vip_message(message, days=7, tier="VIP", db_path=self.db_path)
        
        return message
    
    def build_free_message(
        self,
        tips: List[Dict[str, Any]],
        date_str: str = ""
    ) -> Optional[str]:
        """
        Build FREE message if minimum 3 PRO tips available.
        
        Args:
            tips: Processed tips (will use top 3)
            date_str: Date string
        
        Returns:
            Formatted message or None if not enough tips
        """
        
        # Validate: 3+ PRO tips with odds
        if not validate_tips_for_free(tips):
            log.warning(f"[FREE] Not enough PRO tips: {len(tips)} < 3 required")
            return None
        
        # Format message (takes top 3)
        message = format_free_message(tips[:3], date_str=date_str)
        
        return message
    
    def get_telegram_client(self):
        """Get Telegram bot client (requires python-telegram-bot)."""
        
        try:
            from telegram import Bot
            if not self.bot_token:
                log.error("[TELEGRAM] No TELEGRAM_BOT_TOKEN set")
                return None
            
            return Bot(token=self.bot_token)
        except ImportError:
            log.error("[TELEGRAM] python-telegram-bot not installed")
            return None
    
    async def send_message(
        self,
        message: str,
        chat_id: str,
        buttons: Optional[List[List[Dict[str, str]]]] = None
    ) -> bool:
        """
        Send message to Telegram chat.
        
        Args:
            message: Message text
            chat_id: Telegram chat ID
            buttons: Inline buttons
        
        Returns:
            True if sent successfully
        """
        
        if not chat_id:
            log.error("[TELEGRAM] No chat ID provided")
            return False
        
        try:
            from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
            
            bot = self.get_telegram_client()
            if not bot:
                return False
            
            # Build keyboard if buttons provided
            reply_markup = None
            if buttons:
                keyboard = []
                for row in buttons:
                    button_row = []
                    for btn in row:
                        button_row.append(
                            InlineKeyboardButton(btn["text"], url=btn.get("url"))
                        )
                    keyboard.append(button_row)
                reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send message
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            
            log.info(f"[TELEGRAM] Message sent to {chat_id}")
            return True
        
        except Exception as e:
            log.error(f"[TELEGRAM] Send failed: {repr(e)}")
            return False
    
    async def send_all(
        self,
        vip_tips: List[Dict[str, Any]],
        free_tips: List[Dict[str, Any]],
        date_str: str = ""
    ) -> Dict[str, bool]:
        """
        Send both VIP and FREE messages.
        
        Args:
            vip_tips: VIP tips (6+)
            free_tips: FREE tips (3+)
            date_str: Date string
        
        Returns:
            {vip_sent: bool, free_sent: bool}
        """
        
        results = {"vip_sent": False, "free_sent": False}
        
        # Build VIP message
        vip_msg = self.build_vip_message(vip_tips, date_str=date_str)
        if vip_msg:
            vip_sent = await self.send_message(
                vip_msg,
                self.vip_chat_id,
                buttons=create_inline_buttons_pro()
            )
            results["vip_sent"] = vip_sent
        else:
            log.warning("[VIP] Message not built (insufficient tips)")
        
        # Build FREE message
        free_msg = self.build_free_message(free_tips, date_str=date_str)
        if free_msg:
            free_sent = await self.send_message(
                free_msg,
                self.free_chat_id,
                buttons=create_inline_buttons_pro()
            )
            results["free_sent"] = free_sent
        else:
            log.warning("[FREE] Message not built (insufficient tips)")
        
        return results


# Usage example:
#
# from bot.telegram_integration import TelegramMessageBuilder
#
# builder = TelegramMessageBuilder()
#
# # Process tips
# vip_tips, _ = builder.process_tips(all_tips, tier="VIP")
# free_tips, _ = builder.process_tips(all_tips, tier="FREE")
#
# # Send
# import asyncio
# results = asyncio.run(builder.send_all(vip_tips, free_tips))
# print(results)
