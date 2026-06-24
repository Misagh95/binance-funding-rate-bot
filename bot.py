"""
Binance Funding Rate Monitor Bot
Monitors funding rates on Binance and alerts on high/low rates.
"""
import os
import asyncio
import logging
from typing import Any, Optional
from datetime import datetime

import httpx
from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "15"))
THRESHOLD = float(os.getenv("THRESHOLD", "0.01"))

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

subscribers: set = set()


def is_admin(chat_id: Any) -> bool:
    if not ADMIN_CHAT_ID:
        return True
    return str(chat_id) in ADMIN_CHAT_ID.split(",")


async def fetch_funding_rates() -> Optional[dict]:
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(url, params={"limit": 300})
            if r.status_code == 200:
                data = r.json()
                latest = {}
                for item in data:
                    sym = item["symbol"]
                    if sym not in latest or item["fundingTime"] > latest[sym]['fundingTime']:
                        latest[sym] = item
                return latest
    except Exception as e:
        logger.warning(f"Funding rate fetch failed: {e}")
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    await update.message.reply_text(
        "📈 Binance Funding Rate Monitor\n\n"
        "/subscribe - Subscribe to alerts\n"
        "/unsubscribe - Unsubscribe\n"
        "/rates - Show top funding rates\n"
        "/status - Show status"
    )


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    if not is_admin(update.effective_chat.id):
        return
    subscribers.add(update.effective_chat.id)
    await update.message.reply_text("✅ Subscribed to funding rate alerts.")


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    subscribers.discard(update.effective_chat.id)
    await update.message.reply_text("✅ Unsubscribed.")


async def cmd_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    rates = await fetch_funding_rates()
    if not rates:
        await update.message.reply_text("❌ Failed to fetch rates.")
        return
    sorted_rates = sorted(rates.values(), key=lambda x: abs(float(x['fundingRate'])), reverse=True)[:10]
    lines = ["📊 Top 10 Funding Rates:\n"]
    for item in sorted_rates:
        rate = float(item['fundingRate']) * 100
        emoji = "🟢" if rate >= 0 else "🔴"
        lines.append(f"{emoji} {item['symbol']}: {rate:+.4f}%")
    await update.message.reply_text("\n".join(lines))


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    await update.message.reply_text(f"📊 Subscribers: {len(subscribers)}\nThreshold: {THRESHOLD*100}%")


async def monitor(app: Application) -> None:
    while True:
        try:
            rates = await fetch_funding_rates()
            if not rates:
                await asyncio.sleep(CHECK_INTERVAL)
                continue
            for item in rates.values():
                rate = float(item['fundingRate'])
                if abs(rate) >= THRESHOLD:
                    emoji = "🟢" if rate >= 0 else "🔴"
                    text = (
                        f"🚨 <b>Funding Rate Alert</b>\n\n"
                        f"{emoji} {item['symbol']}: <b>{rate*100:+.4f}%</b>\n"
                        f"Time: {datetime.utcfromtimestamp(item['fundingTime']/1000).strftime('%Y-%m-%d %H:%M UTC')}"
                    )
                    for chat_id in list(subscribers):
                        try:
                            await app.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
                        except Exception as e:
                            logger.warning(f"Alert send failed: {e}")
                        await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)


async def post_init(application: Application) -> None:
    asyncio.create_task(monitor(application))
    commands = [
        BotCommand("start", "Start"),
        BotCommand("subscribe", "Subscribe"),
        BotCommand("unsubscribe", "Unsubscribe"),
        BotCommand("rates", "Top rates"),
        BotCommand("status", "Status"),
    ]
    await application.bot.set_my_commands(commands)


def main() -> None:
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN missing!")
        return
    application = Application.builder().token(TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subscribe", cmd_subscribe))
    application.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))
    application.add_handler(CommandHandler("rates", cmd_rates))
    application.add_handler(CommandHandler("status", cmd_status))
    application.run_polling()


if __name__ == "__main__":
    main()
