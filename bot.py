import os
import html
import random
import logging

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
TMDB_KEY = os.environ.get("TMDB_KEY", "")
REGION = os.environ.get("REGION", "US")  # streaming info country code

TMDB = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/w500"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
log = logging.getLogger("moviebot")


async def tmdb(path: str, **params):
    params["api_key"] = TMDB_KEY
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{TMDB}{path}", params=params)
        r.raise_for_status()
        return r.json()


def results_keyboard(results):
    rows = []
    for m in results[:8]:
        year = (m.get("release_date") or "")[:4] or "N/A"
        title = f"{m.get('title', 'Unknown')} ({year})"
        rows.append([InlineKeyboardButton(title[:60], callback_data=f"m:{m['id']}")])
    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 Movie Info Bot-e swagotom!\n\n"
        "Kono movie-r naam likho, ami details dibo.\n\n"
        "/trending - ekhon trending movie\n"
        "/random - random suggestion\n"
        "/help - sahajjo"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Movie-r naam likho (jemon: Inception), tarpor list theke select koro.\n"
        "Poster, rating, story, cast, trailer, kothay dekha jay shob pabe."
    )


async def trending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = await tmdb("/trending/movie/week")
        await update.message.reply_text(
            "🔥 Ei soptahe trending:", reply_markup=results_keyboard(data["results"])
        )
    except Exception as e:
        log.error("trending error: %s", e)
        await update.message.reply_text("⚠️ Kichu ekta problem hoyeche, abar try koro.")


async def random_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = await tmdb(
            "/discover/movie",
            sort_by="vote_count.desc",
            **{"vote_average.gte": 7, "vote_count.gte": 1000},
            page=random.randint(1, 20),
        )
        pick = random.choice(data["results"])
        await send_movie(update.message.chat_id, pick["id"], context)
    except Exception as e:
        log.error("random error: %s", e)
        await update.message.reply_text("⚠️ Kichu ekta problem hoyeche, abar try koro.")


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = (update.message.text or "").strip()
    if not query:
        return
    try:
        data = await tmdb("/search/movie", query=query, include_adult="false")
        results = data.get("results", [])
        if not results:
            await update.message.reply_text(
                "😕 Kichu paoa jayni. Spelling check kore abar likho."
            )
            return
        await update.message.reply_text(
            f"🔎 '{query}' er result:", reply_markup=results_keyboard(results)
        )
    except Exception as e:
        log.error("search error: %s", e)
        await update.message.reply_text("⚠️ Kichu ekta problem hoyeche, abar try koro.")


async def send_movie(chat_id, movie_id, context: ContextTypes.DEFAULT_TYPE):
    m = await tmdb(
        f"/movie/{movie_id}", append_to_response="videos,credits,watch/providers"
    )

    title = html.escape(m.get("title", "Unknown"))
    year = (m.get("release_date") or "")[:4] or "N/A"
    rating = m.get("vote_average") or 0
    runtime = m.get("runtime") or 0
    genres = ", ".join(g["name"] for g in m.get("genres", [])) or "N/A"
    overview = html.escape(m.get("overview") or "Story paoa jayni.")
    if len(overview) > 450:
        overview = overview[:447] + "..."

    cast = ", ".join(
        html.escape(c["name"]) for c in m.get("credits", {}).get("cast", [])[:5]
    ) or "N/A"

    director = next(
        (
            html.escape(c["name"])
            for c in m.get("credits", {}).get("crew", [])
            if c.get("job") == "Director"
        ),
        "N/A",
    )

    prov = m.get("watch/providers", {}).get("results", {}).get(REGION, {})
    names = [p["provider_name"] for p in prov.get("flatrate", [])[:4]]
    where = html.escape(", ".join(names)) if names else "Info nai"

    caption = (
        f"🎬 <b>{title}</b> ({year})\n"
        f"⭐ {rating:.1f}/10   ⏱ {runtime} min\n"
        f"🎭 {genres}\n"
        f"🎥 Director: {director}\n"
        f"👥 Cast: {cast}\n"
        f"📺 Kothay dekha jay ({REGION}): {where}\n\n"
        f"📖 {overview}"
    )
    if len(caption) > 1024:
        caption = caption[:1020] + "..."

    buttons = []
    trailer = next(
        (
            v
            for v in m.get("videos", {}).get("results", [])
            if v.get("site") == "YouTube" and v.get("type") == "Trailer"
        ),
        None,
    )
    if trailer:
        buttons.append(
            InlineKeyboardButton(
                "▶️ Trailer", url=f"https://www.youtube.com/watch?v={trailer['key']}"
            )
        )
    buttons.append(
        InlineKeyboardButton("ℹ️ TMDB", url=f"https://www.themoviedb.org/movie/{movie_id}")
    )
    markup = InlineKeyboardMarkup([buttons])

    poster = m.get("poster_path")
    if poster:
        await context.bot.send_photo(
            chat_id,
            photo=f"{IMG}{poster}",
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup,
        )
    else:
        await context.bot.send_message(
            chat_id, caption, parse_mode="HTML", reply_markup=markup
        )


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not q.data.startswith("m:"):
        return
    try:
        await send_movie(q.message.chat_id, int(q.data[2:]), context)
    except Exception as e:
        log.error("button error: %s", e)
        await context.bot.send_message(
            q.message.chat_id, "⚠️ Details ante parlam na, abar try koro."
        )


def main():
    if not BOT_TOKEN or not TMDB_KEY:
        raise SystemExit("BOT_TOKEN ar TMDB_KEY set koro (README dekho).")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("trending", trending))
    app.add_handler(CommandHandler("random", random_movie))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search))
    log.info("Bot cholche...")
    app.run_polling()


if __name__ == "__main__":
    main()
