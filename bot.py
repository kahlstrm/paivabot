#!/usr/bin/env python
from datetime import datetime, timedelta
import os
from typing import Tuple
import asyncio
import re
import requests
import libsql_client
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    PollHandler,
    filters,
)

LOOP = asyncio.get_event_loop()
POLL_TIME = timedelta(minutes=10)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEATHER_API = os.getenv("WEATHER_API", "")
DB_URL = os.getenv("DATABASE_URL", "http://127.0.0.1:8080")
DB_TOKEN = os.getenv("DATABASE_TOKEN")
if not BOT_TOKEN or not WEATHER_API:
    print("env variables missing")


class WeatherStatus:
    def __init__(
        self, code: int, temperature: int, votes_yes: int, votes_no: int
    ) -> None:
        self.code = code
        self.temperature = temperature
        self.votes_yes = votes_yes
        self.votes_no = votes_no


weather_code_dict: dict[str, Tuple[WeatherStatus, datetime]] = {}
poll_created_dict: dict[int, Tuple[int, datetime]] = {}

word_filter = [
    "auringonlasku",
    "auringonnousu",
    "auringonpaiste",
    "aurinko",
    "day",
    "halla-aamuja",
    "helleaalto",
    "hurrikaani",
    "ilmankosteus",
    "ilmanpaine",
    "jää",
    "jäätävä sade",
    "jäätyminen",
    "jäätymispisteessä oleva vesi",
    "kaste",
    "keli",
    "korkeapaine",
    "kosteuden lisääntyminen",
    "kosteuden väheneminen",
    "kosteusprosentti",
    "kuurot",
    "kylmä rintama",
    "kylmä",
    "lämmin rintama",
    "lämmin",
    "lämpötila",
    "lämpötilan lasku",
    "lämpötilan nousu",
    "lämpötilan vaihtelu",
    "lumi",
    "lumimyrsky",
    "lumisade",
    "lunta",
    "matalapaine",
    "monsuuni",
    "myrsky",
    "päivä",
    "pakkanen",
    "pilvi",
    "pyörremyrsky",
    "rakeet",
    "sää",
    "sade",
    "salama",
    "sataa",
    "sula",
    "sulaminen",
    "sumu",
    "taifuuni",
    "tornado",
    "tuulennopeus",
    "tuuli",
    "ukkonen",
    "ulkona",
    "weather",
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
        await update.effective_chat.send_message("Error occurred, send help.")
        return
    weather_code_dict[code] = (res, timestamp)
    beautiful_pct = res.votes_yes / (res.votes_no + res.votes_yes) * 100
    beautiness = "Kaunis" if beautiful_pct > 50 else "Ei kaunis"

    await update.effective_chat.send_message(
        f"{weather_desc}: {temp:.1f} °C, {moist} % 💦\nPäivä: {beautiness} ({beautiful_pct:.2f})%"
    )


async def close_poll_sleep(
    update: Update, context: ContextTypes.DEFAULT_TYPE, sleep_time
):
    await asyncio.sleep(sleep_time)
    if update.effective_chat.id in poll_created_dict:
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
    poll_created_dict[chat.id] = (created_poll.id, datetime.now())
    asyncio.run_coroutine_threadsafe(
        close_poll_sleep(update, context, int(POLL_TIME.total_seconds()) - 5), LOOP
    )


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
    async with libsql_client.create_client(
        url=DB_URL, auth_token=DB_TOKEN
    ) as db_client:
        try:
            db_res = await db_client.execute(
                "select code, temperature, votes_yes, votes_no from weather_status where code=? and temperature =?",
                [code, temp_rounded],
            )
            if not db_res.rows:
                db_res = await db_client.execute(
                    "INSERT INTO weather_status(code,temperature,votes_yes,votes_no) VALUES(?,?,?,?) returning *",
                    [code, temp_rounded, yes_amount, no_amount],
                )
            else:
                db_res = await db_client.execute(
                    "UPDATE weather_status SET votes_yes = votes_yes + ?, votes_no = votes_no + ? WHERE code =? AND temperature=? returning *",
                    [yes_amount, no_amount, code, temp_rounded],
                )
        except Exception as e:
            print(e)
            return None, datetime.now() - timedelta(minutes=10)
        row = db_res.rows[0]
        res = WeatherStatus(
            int(row["code"]),
            int(row["temperature"]),
            int(row["votes_yes"]),
            int(row["votes_no"]),
        )
        return res, datetime.now()


async def fetch_from_db(code: str, temp_rounded: int):
    async with libsql_client.create_client(
        url=DB_URL, auth_token=DB_TOKEN
    ) as db_client:
        db_res = await db_client.execute(
            "select code, temperature, votes_yes, votes_no from weather_status where code=? and temperature=?",
            [code, temp_rounded],
        )
        if not db_res.rows:
            db_res = await db_client.execute(
                "INSERT INTO weather_status(code,temperature,votes_yes,votes_no) VALUES(?,?,1,1) returning *",
                [code, temp_rounded],
            )
        row = db_res[0]
        res = WeatherStatus(
            int(row["code"]),
            int(row["temperature"]),
            int(row["votes_yes"]),
            int(row["votes_no"]),
        )
        return res, datetime.now()


def main():
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


if __name__ == "__main__":
    main()
