# (c): Arimov

import logging, requests, asyncio

logging.basicConfig(level=logging.INFO)
from bs4 import BeautifulSoup
from aiohttp.client import ClientSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import *
import swibots as s
from swibots import (
    Client,
    BotContext,
    CommandEvent,
    MessageEvent,
    Grid,
    InlineKeyboardButton,
    InlineMarkup,
    CallbackQueryEvent,
    BotCommand,
    regexp,
)

appBar = s.AppBar("MovieFlix", left_icon=APP_ICON, secondary_icon=SECONDARY_ICON)
app = Client(BOT_TOKEN, app_bar=appBar).set_bot_commands(
    [BotCommand("start", "Get start message", True)]
)

WORK_DOMAIN = "flixhq.pe"
streamCache = {}
detailsCache = {}


async def scrapPage(url="https://flixhq.pe/top-imdb?type=movie"):
    #    print(url)
    async with ClientSession() as ses:
        async with ses.get(url) as res:
            data = BeautifulSoup(await res.read(), "html.parser", from_encoding="utf8")
            return getBlocks(data)


def getBlocks(data):
    res = []
    content = data.find_all("div", "film-poster")
    for acm in content:
        href = acm.find("a").get("href")[1:]
        cm = acm.find("img")
        res.append({"title": cm.get("title"), "image": cm.get("data-src"), "id": href})
    return res


Conf = {}
cacheTrending = []


async def getTrending():
    if cacheTrending:
        return cacheTrending
    async with ClientSession() as ses:
        async with ses.get("https://flixhq.pe/home") as d:
            data = await d.read()
    soup = BeautifulSoup(data, "html.parser", from_encoding="utf8")
    part = soup.find("div", id="trending-movies")
    if not part:
        print(d.status)
        return []
    cacheTrending.extend(getBlocks(part))
    return cacheTrending


async def makeHome():
    async with ClientSession() as ses:
        async with ses.get("https://flixhq.pe/home") as d:
            data = await d.read()
    soup = BeautifulSoup(data, "html.parser", from_encoding="utf8")
    divs = soup.find_all("div", "swiper-slide")
    res = []
    for dv in divs:
        y = dv.find("a").get("href")[1:]
        img = dv.get("style").split("(")[-1].split(")")[0]
        res.append({"image": img, "id": y})
    return res


@app.on_command("start")
async def startMessage(ctx: BotContext[CommandEvent]):
    await ctx.event.message.reply_text(
        f"Hi, I am {ctx.user.name}",
        inline_markup=InlineMarkup(
            [[InlineKeyboardButton("Open", callback_data="open")]]
        ),
    )


@app.on_callback_query(regexp("stream_(.*)"))
async def showCallback(ctx: BotContext[CallbackQueryEvent]):
    m = ctx.event.message
    data = ctx.event.callback_data.split("_")[-1].split("|")
    #    print(data)
    id = data[1]
    user = ctx.event.action_by_id
    print(id, data)

    took = 0
    while not Conf.get(user):
        await asyncio.sleep(0.2)
        took += 0.2
        if took > 2:
            break
    quality = Conf.get(user) or "auto"
    print(data[0], data[1])
    if "movie/" in data[1] and streamCache.get(data[1]):
        stream = streamCache.get(data[1])
    else:
        stream = requests.get(
            f"https://button-dusky.vercel.app/movies/flixhq/watch?episodeId={data[0]}&mediaId={data[1]}"
        ).json()
        if "movie/" in data[1]:
            streamCache[data[1]] = stream

    url = None
    print(id, data, stream)
    details = (
        detailsCache.get(id)
        or requests.get(
            f"https://button-dusky.vercel.app/movies/flixhq/info?id={id}"
        ).json()
    )
    detailsCache[id] = details
    if not stream.get("sources"):
        await ctx.event.answer("Something went wrong!", show_alert=True)
        return
    for src in stream["sources"]:
        if src["quality"] == quality:
            url = src["url"]
            break
    if not url and stream["sources"]:
        url = stream["sources"][-1]["url"]
    if not url:
        await ctx.event.answer("URL Not found!", show_alert=True)
        return
    #    print(stream)
    lays, comps = [], []
    comps.append(
        s.VideoPlayer(
            url,
            title=details.get("title", ""),
            subtitle=(
                str(details["rating"]) + "/10"
                if details.get("rating")
                else details.get("releaseDate")
            ),
        )
    )
    if details.get("genres"):
        comps.append(s.Text("🥡 Genre", s.TextSize.SMALL))
        comps.append(s.Text(" | ".join(details["genres"])))
    if details.get("description"):
        comps.append(s.Text("⌛ Description", s.TextSize.SMALL))
        comps.append(s.Text(details["description"].strip()))

    if details.get("releaseDate"):
        comps.append(s.Text("🕛 Release Date:" + " " + details.get("releaseDate", "")))
    for y in ["Country", "Production", "Duration"]:
        d = details.get(y.lower())
        if not d:
            continue
        comps.append(s.Text(y, s.TextSize.SMALL))
        comps.append(s.Text(d))

    if details.get("recommendations"):
        childs = []
        for dt in details["recommendations"]:
            if "movie/" in dt["id"]:
                mId = dt["id"].split("-")[-1]
                cd = f"stream_{mId}|{dt['id']}"
            else:
                cd = f"call_{dt['id']}"
            #            print(cd)
            childs.append(
                s.GridItem(
                    title=dt["title"][:18],
                    media=dt["image"].replace("flixhq.to", "flixhq.pe"),
                    selective=True,
                    callback_data=cd,
                )
            )

        lays.append(
            s.Grid(
                title="Recommended",
                expansion=s.Expansion.EXPAND,
                size=3,
                horizontal=True,
                options=childs,
            )
        )
    await ctx.event.answer(
        callback=s.AppPage(
            components=comps,
            layouts=lays,
        ),
        new_page=True,
    )


@app.on_callback_query(regexp("call_(.*)"))
async def showCallback(ctx: BotContext[CallbackQueryEvent]):
    m = ctx.event.message

    data = ctx.event.callback_data.split("_")[-1]
    print(data)
    details = (
        detailsCache.get(data)
        or requests.get(
            f"https://button-dusky.vercel.app/movies/flixhq/info?id={data}"
        ).json()
    )
    detailsCache[data] = details
    lays, comps = [], []
    comps.append(s.Text(details.get("title", ""), s.TextSize.SMALL))
    comps.append(s.Text("Release: " + details.get("releaseDate", "")))
    comps.append(s.Text("Type: " + details["type"], s.TextSize.SMALL))
    comps.append(
        s.Dropdown(
            "Select Episode",
            options=[
                s.ListItem(
                    f"Episode {d.get('number') or d.get('id')}",
                    callback_data=f"stream_{d['id']}|{details['id']}",
                )
                for d in details["episodes"][::-1]
            ],
        ),
    )
    comps.append(
        s.Dropdown(
            "Select Quality",
            options=[
                s.ListItem(d, callback_data=f"select_{d}")
                for d in ["default", "1080p", "720p", "480p", "360p"]
            ],
        ),
    )

    await ctx.event.answer(
        callback=s.AppPage(components=comps, layouts=lays, screen=s.ScreenType.BOTTOM),
        new_page=True,
    )


Glob = {}

pages = [
    {"id": "10-24", "name": "Action"},
    {"id": "12", "name": "Romance"},
    {"id": "7", "name": "Comedy"},
    {"id": "4", "name": "Drama"},
    {"id": "13", "name": "Fantasy"},
    {"id": "14", "name": "Horror"},
    {"id": "16", "name": "Thriller"},
    {"id": "all", "name": "TV Shows", "type": "tv"},
]


@app.on_callback_query(regexp("search$"))
async def showCallback(ctx: BotContext[CallbackQueryEvent]):
    #    await ctx.event.message.send(ctx.event.callback_data)
    m = ctx.event.message
    lays, comps = [], [
        s.SearchBar(
            "Search Movies..",
            callback_data="searchMovie",
            label="Find the desired content",
            left_icon="https://f004.backblazeb2.com/file/switch-bucket/894f6214-a98f-11ee-9962-d41b81d4a9ef.png",
            right_icon="https://f004.backblazeb2.com/file/switch-bucket/cf431478-a98f-11ee-81e5-d41b81d4a9ef.png",
        ),
    ]
    Glob[ctx.event.action_by_id] = ctx.event.query_id
    await ctx.event.answer(callback=s.AppPage(components=comps, layouts=lays))


@app.on_callback_query(regexp("searchMovie"))
async def showCallback(ctx: BotContext[CallbackQueryEvent]):
    m = ctx.event.message
    query = ctx.event.details.get("searchQuery")
    if not query:
        return await ctx.event.answer("Provide a query to search", show_alert=True)
    lays, comps = [], [
        s.SearchBar(
            "Search Movies..",
            callback_data="searchMovie",
            label="Find the desired content",
            value=query,
            left_icon="https://f004.backblazeb2.com/file/switch-bucket/894f6214-a98f-11ee-9962-d41b81d4a9ef.png",
            right_icon="https://f004.backblazeb2.com/file/switch-bucket/cf431478-a98f-11ee-81e5-d41b81d4a9ef.png",
        ),
    ]
    details = requests.get(
        f"https://button-dusky.vercel.app/movies/flixhq/{query}"
    ).json()
    childs = []
    for dt in details["results"]:
        #        if "tv/" in dt["id"]:
        #           continue
        if "movie/" in dt["id"]:
            mId = dt["id"].split("-")[-1]
            cd = f"stream_{mId}|{dt['id']}"
        else:
            cd = f"call_{dt['id']}"
        #            print(cd)
        childs.append(
            s.GridItem(
                title=dt["title"][:18],
                media=dt["image"].replace("flixhq.to", "flixhq.pe"),
                selective=True,
                callback_data=cd,
            )
        )

    lays.append(
        s.Grid(
            f"Search Results for {query}...",
            expansion=s.Expansion.EXPAND,
            options=childs,
        )
    )
    print("Calling on", Glob.get(ctx.event.action_by_id))
    await ctx.event.answer(callback=s.AppPage(components=comps, layouts=lays))


@app.on_callback_query(regexp("more(.*)"))
async def showCallback(ctx: BotContext[CallbackQueryEvent]):
    m = ctx.event.message

    data = query = ctx.event.callback_data.split("|")[-1]
    if data == "imdb":
        data = await scrapPage()
        name = "IMDB"
    elif data == "trend":
        data = await getTrending()
        name = "Trending"
    else:
        dnmt = list(filter(lambda x: x["id"] == query, pages))[0]
        url = (
            f"https://flixhq.pe/filter?type="
            + dnmt.get("type", "movie")
            + f"&quality=all&release_year=all&genre={data}&country=105"
        )
        data = await scrapPage(url)
        print(data, pages)
        name = dnmt["name"]
    lays, comps = [], []
    childs = []
    for dt in data:
        if "movie/" in dt["id"]:
            mId = dt["id"].split("-")[-1]
            cd = f"stream_{mId}|{dt['id']}"
        else:
            cd = f"call_{dt['id']}"
        #            print(cd)
        childs.append(
            s.GridItem(
                title=dt["title"][:18],
                media=dt["image"],
                selective=True,
                callback_data=cd,
            )
        )

    lays.append(s.Grid(name, expansion=s.Expansion.EXPAND, options=childs))
    await ctx.event.answer(callback=s.AppPage(components=comps, layouts=lays))


@app.on_callback_query(regexp("open"))
async def showCallback(ctx: BotContext[CallbackQueryEvent]):
    #    await ctx.event.message.send(ctx.event.callback_data)
    caras = await makeHome()
    m = ctx.event.message

    lays, comps = [], [
        s.SearchHolder("Search Movies", callback_data="search"),
    ]
    lays.append(
        s.Carousel(
            [
                s.Image(
                    url=dd["image"],
                    callback_data=(
                        f"stream_{dd['id'].split('-')[-1]}|{dd['id']}"
                        if "movie/" in dd["id"]
                        else "call_" + dd["id"]
                    ),
                )
                for dd in caras
            ]
        )
    )
    # print(lays)

    res = await scrapPage()

    async def fetch(index, y):
        if y.get("data"):
            return
        #        print(index, y)
        url = (
            f"https://flixhq.pe/filter?type="
            + y.get("type", "movie")
            + f"&quality=all&release_year=all&genre={y['id']}&country=105"
        )
        y["data"] = await scrapPage(url)
        pages[index] = y

    await asyncio.gather(*[fetch(index, y) for index, y in enumerate(pages)])
    trend = await getTrending()
    childs = []
    for dt in trend[:10]:
        if "movie/" in dt["id"]:
            mId = dt["id"].split("-")[-1]
            cd = f"stream_{mId}|{dt['id']}"
        else:
            cd = f"call_{dt['id']}"
        #            print(cd)
        childs.append(
            s.GridItem(
                title=dt["title"][:18],
                media=dt["image"],
                selective=True,
                callback_data=cd,
            )
        )

    lays.append(
        Grid(
            title="Trending",
            horizontal=True,
            expansion=s.Expansion.EXPAND,
            image_callback="more|trend",
            right_image="https://f004.backblazeb2.com/file/switch-bucket/9c99cba4-a988-11ee-8ef4-d41b81d4a9ef.png",
            options=childs,
        )
    )

    childs = []
    for dt in res[:10]:
        if "movie/" in dt["id"]:
            mId = dt["id"].split("-")[-1]
            cd = f"stream_{mId}|{dt['id']}"
        else:
            cd = f"call_{dt['id']}"
        #            print(cd)
        childs.append(
            s.GridItem(
                title=dt["title"][:18],
                media=dt["image"],
                selective=True,
                callback_data=cd,
            )
        )

    lays.append(
        Grid(
            title="Top IMDB",
            horizontal=True,
            expansion=s.Expansion.EXPAND,
            image_callback="more|imdb",
            right_image="https://f004.backblazeb2.com/file/switch-bucket/9c99cba4-a988-11ee-8ef4-d41b81d4a9ef.png",
            options=childs,
        )
    )
    for page in pages:
        data = page.get("data") or await scrapPage(
            f"https://flixhq.pe/filter?type=movie&quality=all&release_year=all&genre={page['id']}&country=105"
        )
        childs = []
        for dt in data[:10]:
            if "movie/" in dt["id"]:
                mId = dt["id"].split("-")[-1]
                cd = f"stream_{mId}|{dt['id']}"
            else:
                cd = f"call_{dt['id']}"
            #            print(cd)
            childs.append(
                s.GridItem(
                    title=dt["title"][:18],
                    media=dt["image"],
                    selective=True,
                    callback_data=cd,
                )
            )
        lays.append(
            Grid(
                title=page["name"],
                horizontal=True,
                expansion=s.Expansion.EXPAND,
                image_callback=f"more|{page['id']}",
                right_image="https://f004.backblazeb2.com/file/switch-bucket/9c99cba4-a988-11ee-8ef4-d41b81d4a9ef.png",
                options=childs,
            )
        )

    await ctx.event.answer(callback=s.AppPage(components=comps, layouts=lays))


async def clean():
    cacheTrending.clear()
    for y in pages:
        if y.get("data"):
            del y["data"]

    await getTrending()


sched = AsyncIOScheduler()
sched.add_job(clean, "interval", days=1)
sched.start()

app.run()
