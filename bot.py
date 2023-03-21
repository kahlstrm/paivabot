from datetime import datetime, timedelta
import os
import time
from typing import Tuple
import asyncio
import re
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    PollHandler,
    filters,
)
from prisma import Prisma
from prisma.models import WeatherIcon


load_dotenv()
POLL_TIME = timedelta(minutes=10)
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEATHER_API = os.getenv("WEATHER_API")
if not BOT_TOKEN or not WEATHER_API:
    print("env variables missing")
weather_code_dict: dict[str, Tuple[WeatherIcon, datetime]] = {}
poll_created_dict: dict[int, Tuple[int, datetime]] = {}

word_filter = [
    "päivä",
    "day",
    "sää",
    "keli",
    "weather",
    "ulkona",
    "kylmä",
    "lämmin",
    "sataa",
    "sade",
    "lunta",
    "lumi",
]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!"
    )


def poll_active(created_at: datetime):
    return datetime.now() - created_at < POLL_TIME


def fetch_weather():
    weather = requests.get(
        f"https://api.openweathermap.org/data/2.5/weather?q=otaniemi&appid={WEATHER_API}&units=metric&lang=fi"
    )
    weather = weather.json()
    return weather


async def day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    weather = fetch_weather()
    descriptives = weather["weather"][0]
    weather_desc = descriptives["description"]
    code = descriptives["id"]
    measurements = weather["main"]
    temp = float(measurements["temp"])
    temp_rounded = int(5 * (temp // 5))
    moist = measurements["humidity"]
    if code in weather_code_dict:
        (res, timestamp) = weather_code_dict[code]
        if (datetime.now() - timestamp).total_seconds() > 300:
            res, timestamp = await fetch_from_db(code, temp_rounded)
    else:
        res, timestamp = await fetch_from_db(code, temp_rounded)
    if not res:
        res, timestamp = await add_data_to_db(code, temp_rounded, 1, 1)
    if not res:
        await update.effective_chat.send_message(f"Error occurred, send help.")
    weather_code_dict[code] = (res, timestamp)
    beautiful_pct = res.votes_yes / (res.votes_no + res.votes_yes) * 100
    beautiness = "Kaunis" if beautiful_pct > 50 else "Ei kaunis"

    await update.effective_chat.send_message(
        f"{weather_desc}: {temp:.1f} °C, {moist} % 💦\nPäivä: {beautiness} ({beautiful_pct:.2f})%"
    )


async def close_poll_sleep(
    update: Update, context: ContextTypes.DEFAULT_TYPE, sleep_time
):
    time.sleep(sleep_time)
    await close_poll(update, context)


async def start_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.id in poll_created_dict:
        poll_created = poll_created_dict[chat.id][1]
        if poll_active(poll_created):
            return await update.message.reply_text(
                "Äänestys on jo käynnissä!\nA vote is already in progress!"
            )
    created_poll = await chat.send_poll(
        "Onko tänään kaunis päivä?\n Is it beautiful day today?",
        ["Kyllä/Yes", "Ei/No"],
        close_date=(datetime.now() + POLL_TIME),
    )
    asyncio.create_task(
        close_poll_sleep(update, context, int(POLL_TIME.total_seconds()) - 5)
    )
    poll_created_dict[chat.id] = (created_poll.id, datetime.now())


async def close_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in poll_created_dict or not poll_active(
        poll_created_dict[chat_id][1]
    ):
        print("close_poll")
        return await update.effective_chat.send_message(
            "Ei aktiivista äänestystä chatissa!\nNo active poll in chat"
        )
    poll_id = poll_created_dict[chat_id][0]
    await context.bot.stop_poll(chat_id, poll_id)
    del poll_created_dict[chat_id]
    await update.effective_chat.send_message("Äänestys suljettu\nPoll closed.")


async def handle_poll_ended(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("handle_poll_ended")
    if not update.poll.is_closed:
        return
    choices = update.poll.options
    yes_amount = [option.voter_count for option in choices if "Kyllä" in option.text][0]
    no_amount = [option.voter_count for option in choices if "Ei" in option.text][0]
    weather = fetch_weather()
    code = weather["weather"][0]["id"]
    temp = float(weather["main"]["temp"])
    temp_rounded = int(5 * (temp // 5))
    weather = await add_data_to_db(code, temp_rounded, yes_amount, no_amount)
    if code in weather_code_dict:
        del weather_code_dict[code]


async def add_data_to_db(code: int, temp_rounded: int, yes_amount: int, no_amount: int):
    db = Prisma()
    try:
        await db.connect()
        res = await db.weathericon.find_first(
            where={"code": code, "temperature": temp_rounded}
        )
        if not res:
            res = await db.weathericon.create(
                data={
                    "code": code,
                    "temperature": temp_rounded,
                    "votes_yes": yes_amount,
                    "votes_no": no_amount,
                }
            )
        else:
            await db.weathericon.update_many(
                where={
                    "code": code,
                    "temperature": temp_rounded,
                },
                data={
                    "votes_yes": {"increment": yes_amount},
                    "votes_no": {"increment": no_amount},
                },
            )
    except Exception as e:
        print(e)
        return None, datetime.now() - timedelta(minutes=10)
    finally:
        await db.disconnect()
    return res, datetime.now()


async def fetch_from_db(code: str, temp_rounded: int):
    db = Prisma()
    try:
        await db.connect()
        db_res = await db.weathericon.find_first(
            where={"code": code, "temperature": temp_rounded}
        )
        if not db_res:
            db_res = await db.weathericon.create(
                {"code": code, "temperature": temp_rounded}
            )
    finally:
        if db.is_connected():
            await db.disconnect()
    return db_res, datetime.now()


if __name__ == "__main__":
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    start_handler = CommandHandler("start", start)
    day_handler = CommandHandler("paiva", day)
    vote_handler = CommandHandler(["vote", "aanesta"], start_poll)
    close_handler = CommandHandler(["close", "sulje"], close_poll)
    poll_hander = PollHandler(handle_poll_ended)
    message_handler = MessageHandler(
        filters=(
            filters.CHAT
            & filters.Regex(re.compile("|".join(word_filter), re.IGNORECASE))
        ),
        callback=day,
    )
    application.add_handlers(
        [
            start_handler,
            vote_handler,
            day_handler,
            poll_hander,
            close_handler,
            message_handler,
        ]
    )
    application.run_polling()
