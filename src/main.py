from telegram.ext import (Updater,
                          CommandHandler,
                          MessageHandler,
                          Filters,
                          CallbackContext,
                          InlineQueryHandler,
                          )
from telegram import (Bot,
                      ReplyKeyboardMarkup,
                      KeyboardButton,
                      Update,
                      ReplyKeyboardRemove,
                      InlineQueryResult
                      )
import os
import logging
import json
from typing import (Optional, Union,
                    List,
                    Tuple,
                    TypedDict,
                    cast
                    )
from enum import Enum
from telegram.inline.inlinequeryresultphoto import InlineQueryResultPhoto
from telegram.inline.inlinequeryresultarticle import InlineQueryResultArticle
from telegram.inline.inputtextmessagecontent import InputTextMessageContent

from telegram.message import Message
import urllib.parse
import urllib.request
import requests
from db import Backend, Location
from weatherProvider import fetchAndPlot, getLocationInfo
import base64

db = Backend()


class ButtonQueryType(str, Enum):
    GET = 'get'
    RENAME = 'rename'


class ButtonQuery(TypedDict):
    type: ButtonQueryType
    name: str
    newName: Optional[str]


def start(update: Update, context: CallbackContext):
    context.bot.send_message(
        chat_id=update.effective_chat.id, text="Send me locations and I will answer with the weather.")


def sendForecast(chat_id: Union[int, str], bot: Bot, lat: float, lon: float, detailed: bool, name: str = None):
    waitingMessage = bot.send_message(chat_id, text="⏳")
    result = fetchAndPlot(lat, lon, 10 if detailed else 1.5)
    station_text = f"forecast for {name}." if (
        name != None) else f"forecast for {result['weather_station']} ({result['weather_station_distance']}km from location)."
    bot.send_photo(chat_id,
                   photo=open(result['plot'], 'rb'),
                   caption=f"{result['duration']} day {station_text}\nCurrently it is {result['current_temp']}°C and {result['current_str']}.",
                   reply_markup=ReplyKeyboardRemove())
    bot.delete_message(chat_id=chat_id, message_id=waitingMessage.message_id)


def getStuff(update: Update) -> Tuple[str, Message]:
    message = None
    if update.edited_message:
        message = update.edited_message
    else:
        message = update.message
    return (update.effective_chat.id, message)


def addLocation(chat_id: str, bot: Bot, lat: float, lon: float):
    name, dist = getLocationInfo(lat, lon)
    if db.addLocation(chat_id, {
        'name': name,
        'lat': lat,
        'lon': lon
    }):
        bot.send_message(
            chat_id, f"Station '{name}' ({dist}km from location) added.\nIt will be included in '/getall' and you can get it individually by '/get {name}'.")
    else:
        bot.send_message(chat_id, f"Station '{name}' is already added.")


def getAll(update: Update, context: CallbackContext):
    chat_id, _ = getStuff(update)
    locations = list(db.getLocations(chat_id))
    if len(locations) == 0:
        context.bot.send_message(
            chat_id, text=f"You need to add a location with '/add'.")
        return

    for location in locations:
        sendForecast(chat_id, context.bot,
                     location['lat'], location['lon'], False, name=location['name'])


def callbackDataGet(name: str) -> str:
    return json.dumps({
        'type': ButtonQueryType.GET,
        'name': name
    })


def locationReplyKeyboard(locations: List[Location]) -> ReplyKeyboardMarkup:
    locationNames = list(map(lambda x: x['name'], locations))

    keyboard = []
    i = 0
    while i < len(locationNames) - 1:
        keyboard.append([
            KeyboardButton(
                locationNames[i], callback_data=callbackDataGet(locationNames[i])),
            KeyboardButton(
                locationNames[i + 1], callback_data=callbackDataGet(locationNames[i + 1])),
        ])
        i += 2

    if len(locationNames) - i == 1:
        keyboard.append([
            KeyboardButton(
                locationNames[i], callback_data=callbackDataGet(locationNames[i]))
        ])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)


def getWrapper(update: Update, context: CallbackContext, detailed: bool):
    chat_id, message = getStuff(update)
    logging.log(level=logging.INFO, msg=f"Cid: {type(chat_id)}")
    locations = list(db.getLocations(chat_id))
    if len(locations) == 0:
        context.bot.send_message(
            chat_id, text=f"You need to add a location with '/add'.")
        return

    locationNames = list(map(lambda x: x['name'], locations))
    if context.args != None and len(context.args) == 0:
        db.setState(chat_id, {'type': 'getDetailed' if detailed else 'get'})
        message.reply_text(
            'Choose a station.', reply_markup=locationReplyKeyboard(locations))
        return

    if context.args[0] not in locationNames:
        context.bot.send_message(
            chat_id, text=f"You have not added {context.args[0]}.\n You have added {', '.join(locationNames)}.")
        return
    location = next(filter(lambda x: x['name'] == context.args[0], locations))
    sendForecast(chat_id, context.bot,
                 location['lat'], location['lon'], detailed, name=location['name'])


def get(update: Update, context: CallbackContext):
    getWrapper(update, context, False)


def getDetailed(update: Update, context: CallbackContext):
    getWrapper(update, context, True)


def handleLocation(update: Update, context: CallbackContext):
    chat_id, message = getStuff(update)
    lat = message.location.latitude
    lon = message.location.longitude
    if db.getState(chat_id)['type'] == 'add':  # type: ignore
        addLocation(chat_id, context.bot, lat, lon)
        db.setState(chat_id, {'type': 'idle'})
    else:
        sendForecast(chat_id, context.bot, lat, lon, False)


def add(update: Update, context: CallbackContext):
    chat_id, message = getStuff(update)
    db.setState(chat_id, {'type': 'add'})
    context.bot.send_message(chat_id, text="Ok, now send a location.")


def handleText(update: Update, context: CallbackContext):
    chat_id, message = getStuff(update)
    state = db.getState(chat_id)
    db.setState(chat_id, {'type': 'idle'})

    if state['type'] == 'get' or state['type'] == 'getDetailed':  # type: ignore
        locations = db.getLocations(chat_id)
        location = next(
            filter(lambda x: x['name'] == message.text, locations), None)
        if location != None:
            sendForecast(chat_id, context.bot,
                         location['lat'], location['lon'], name=location['name'], detailed=state['type'] == 'get')  # type: ignore
        else:
            context.bot.send_message(
                chat_id, text="Invalid station name.", reply_markup=ReplyKeyboardRemove())

    elif state['type'] == 'rename':  # type: ignore
        locations = db.getLocations(chat_id)

        # new name
        if 'location' in state:
            location = next(filter(lambda x: x['name'] == state['location']['name'], locations), None)  # type: ignore
            if location != None:
                db.renameLocation(chat_id, location, message.text)
                context.bot.send_message(
                    chat_id, f"'{state['location']['name']}' was renamed to '{message.text}'")
            else:
                context.bot.send_message(
                    chat_id, text="Invalid station name.", reply_markup=ReplyKeyboardRemove())
            return

        location = next(
            filter(lambda x: x['name'] == message.text, locations), None)
        if location != None:
            db.setState(chat_id, {'type': 'rename', 'location': location})
            context.bot.send_message(
                chat_id, text="Ok. What is the new name?", reply_markup=ReplyKeyboardRemove())
        else:
            context.bot.send_message(
                chat_id, text="Invalid station name.", reply_markup=ReplyKeyboardRemove())


def rename(update: Update, context: CallbackContext):
    chat_id, message = getStuff(update)
    db.setState(chat_id, {'type': 'rename'})

    locations = list(db.getLocations(chat_id))
    if len(locations) == 0:
        context.bot.send_message(
            chat_id, text=f"You need to add a location with '/add'.")
        return

    message.reply_text(
        'Choose a station to rename.', reply_markup=locationReplyKeyboard(locations))


def handleInlineQuery(update: Update, context: CallbackContext):
    query = update.inline_query.query

    locationResults = {}
    with urllib.request.urlopen(f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(query, safe='')}&addressdetails=1&format=jsonv2") as url:
        locationResults = json.loads(url.read().decode())

    answers: List[InlineQueryResult] = []
    for locationResult in locationResults[:1]:
        imageResult = fetchAndPlot(locationResult['lat'], locationResult['lon'], 10, jpeg=True)

        url = "https://api.imgur.com/3/image"
        payload = {'image': base64.b64encode(open(imageResult['plot'], 'rb').read())}
        headers = {
            'Authorization': f"Client-ID {os.environ.get('IMGUR_CLIENT_ID')}"
        }
        uploadResponse = requests.request("POST", url, headers=headers, data=payload, files=[])
        # logging.log(msg=uploadResponse.text, level=20)
        uploadJson = json.loads(uploadResponse.text)
        link = uploadJson['data']['link']

        answers.append(
            InlineQueryResultPhoto(
                id=uploadJson['data']['id'],
                photo_url=link,
                thumb_url=link.replace('.jpg', 's.jpg'),
                photo_height=uploadJson['data']['height'],
                photo_width=uploadJson['data']['width'],
                description=f"Weather for {imageResult['weather_station']}",
                caption=f"Weather for {imageResult['weather_station']}",
                title=imageResult['weather_station'],
            )
        )
    context.bot.answer_inline_query(update.inline_query.id, results=answers, cache_time=10)

updater = Updater(token=os.environ.get('BOT_TOKEN'))
dispatcher = updater.dispatcher

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(CommandHandler('add', add))
dispatcher.add_handler(CommandHandler('getAll', getAll))
dispatcher.add_handler(CommandHandler('get', get))
dispatcher.add_handler(CommandHandler('getDetailed', getDetailed))
dispatcher.add_handler(CommandHandler('rename', rename))
dispatcher.add_handler(MessageHandler(Filters.location, handleLocation))
dispatcher.add_handler(MessageHandler(Filters.text, handleText))
dispatcher.add_handler(InlineQueryHandler(handleInlineQuery))


updater.start_polling()
