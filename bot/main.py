from numpy import imag
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
from typing import (Any, Literal, Optional, Union,
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
from weatherProvider import debugTest, fetchAndPlot, getLocationInfo
import threading
import functools

db = Backend()


class ButtonQuery(TypedDict):
    type: Literal['get', 'rename']
    name: str
    newName: Optional[str]


class ImageResult(TypedDict):
    imageId: str
    imageLink: str
    thumbLink: str
    duration: float
    current_temp: float
    current_str: str
    weather_station: str
    weather_station_distance: float
    width: int
    height: int


class UploadResult(TypedDict):
    id: str
    link: str
    thumb: str
    width: int
    height: int


def start(update: Update, context: CallbackContext):
    context.bot.send_message(chat_id=update.effective_chat.id, text="Send me locations and I will answer with the weather.")


@functools.lru_cache(maxsize=100, typed=False)
def getImage(lat: float, lon: float, tenDays: bool) -> Optional[ImageResult]:
    imageResult = fetchAndPlot(lat, lon, 10 if tenDays else 1.5)
    if imageResult == None:
        return None

    url = "http://image-host/image"
    files = {'image': imageResult['plot'].read()}

    uploadResponse = requests.request("POST", url, files=files)
    uploadJson = cast(UploadResult, json.loads(uploadResponse.text))
    return {
        'imageId': uploadJson['id'],
        'imageLink': uploadJson['link'],
        'thumbLink': uploadJson['thumb'],
        'width': uploadJson['width'],
        'height': uploadJson['height'],
        'duration': imageResult['duration'],
        'current_temp': imageResult['current_temp'],
        'current_str': imageResult['current_str'],
        'weather_station': imageResult['weather_station'],
        'weather_station_distance': imageResult['weather_station_distance'],
    }


def clearCache():
    logging.log(msg=getImage.cache_info(), level=20)
    logging.log(msg="clearing cache", level=20)
    getImage.cache_clear()
    threading.Timer(60 * 30, clearCache).start()


def sendForecast(chat_id: Union[int, str], bot: Bot, lat: float, lon: float, detailed: bool, name: str = None):
    waitingMessage = bot.send_message(chat_id, text="⏳")
    try:
        result = getImage(lat, lon, detailed)
        if result == None:
            bot.send_message(chat_id, text="The location has no weather data.")
            return

        station_text = f"forecast for {name}." if (
            name != None) else f"forecast for {result['weather_station']} ({result['weather_station_distance']}km from location)."
        bot.send_photo(chat_id,
                       photo=result['imageLink'],
                       caption=f"{result['duration']} day {station_text}\nCurrently it is {result['current_temp']}°C and {result['current_str']}.",
                       reply_markup=ReplyKeyboardRemove())
    except:
        bot.send_message(chat_id, text="Uh oh, an error occured.")
    finally:
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
        sendForecast(chat_id, bot, lat, lon, True)
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
                     location['lat'], location['lon'], True, name=location['name'])


def locationReplyKeyboard(locations: List[Location]) -> ReplyKeyboardMarkup:
    locationNames = list(map(lambda x: x['name'], locations))

    keyboard = []
    i = 0
    while i < len(locationNames) - 1:
        keyboard.append([locationNames[i], locationNames[i + 1]])
        i += 2

    if len(locationNames) - i == 1:
        keyboard.append([locationNames[i]])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)


def getWrapper(update: Update, context: CallbackContext, detailed: bool):
    chat_id, message = getStuff(update)
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
    location = next(filter(lambda x: x['name'] == context.args[0], locations), None)
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
        sendForecast(chat_id, context.bot, lat, lon, True)


def add(update: Update, context: CallbackContext):
    chat_id, message = getStuff(update)
    db.setState(chat_id, {'type': 'add'})
    context.bot.send_message(chat_id, text="Ok, now send a location.")


def handleText(update: Update, context: CallbackContext):
    chat_id, message = getStuff(update)
    state = db.getState(chat_id)
    db.setState(chat_id, {'type': 'idle'})

    if state['type'] == 'get' or state['type'] == 'getDetailed':  # type: ignore
        if 'addLocations' in state:
            selectedLocation = next(filter(lambda l: l['name'] == message.text, state['addLocations']), None)
            if selectedLocation != None:
                sendForecast(chat_id, context.bot, selectedLocation['lat'], selectedLocation['lon'], True)
            else:
                context.bot.send_message(chat_id, text="Invalid location selected.", reply_markup=ReplyKeyboardRemove())
            db.setState(chat_id, {'type': 'idle'})
        else:
            locations = db.getLocations(chat_id)
            location = next(filter(lambda x: x['name'] == message.text, locations), None)
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
    elif state['type'] == 'add':  # type: ignore
        if 'addLocations' in state:
            selectedLocation = next(filter(lambda l: l['name'] == message.text, state['addLocations']), None)
            if selectedLocation != None:
                addLocation(chat_id, context.bot, selectedLocation['lat'], selectedLocation['lon'])
            else:
                context.bot.send_message(chat_id, text="Invalid location selected.", reply_markup=ReplyKeyboardRemove())
            db.setState(chat_id, {'type': 'idle'})
        else:
            addLocations = queryLocations(message.text)
            if len(addLocations) > 0:
                db.setState(chat_id, {
                    'type': 'add',
                    'addLocations': addLocations
                })
                context.bot.send_message(chat_id,
                                        text="I have found these locations matching. Choose one:",
                                         reply_markup=locationReplyKeyboard(addLocations))
            else:
                context.bot.send_message(chat_id,
                                        text="I couldn't find a location.",
                                        reply_markup=ReplyKeyboardRemove())
    elif state['type'] == 'idle' and message.chat.type == 'private':  # type: ignore
        addLocations = queryLocations(message.text)
        if len(addLocations) > 0:
            db.setState(chat_id, {
                'type': 'get',
                'addLocations': addLocations
            })
            context.bot.send_message(chat_id,
                                    text="I have found these locations matching. Choose one:",
                                    reply_markup=locationReplyKeyboard(addLocations))
        else:
            context.bot.send_message(chat_id,
                                     text="I couldn't find a location.",
                                     reply_markup=ReplyKeyboardRemove())




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


def osmToLocation(element: Any) -> Location:
    return {
        'lat': element['lat'],
        'lon': element['lon'],
        'name': element['display_name']
    }


def queryLocations(query: str) -> List[Location]:
    with urllib.request.urlopen(f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(query, safe='')}&format=jsonv2") as url:
        return list(map(osmToLocation, json.loads(url.read().decode())))


currentQueryResult = {}


def handleInlineQuery(update: Update, context: CallbackContext):
    query = update.inline_query.query
    queryId = update.inline_query.id
    currentOffset = update.inline_query.offset
    if currentOffset == 'None':
        return
    try:
        currentOffset = int(currentOffset)
    except:
        currentOffset = 0
    logging.log(msg=f"{queryId} ({query}): current offset: {currentOffset}", level=20)

    locationResults = {}
    if queryId in currentQueryResult:
        logging.log(msg=f"{queryId} ({query}): using cache", level=20)
        locationResults = currentQueryResult[queryId]
    else:
        locationResults = queryLocations(query)
        currentQueryResult[queryId] = locationResults

    answers: List[InlineQueryResult] = []

    while len(answers) == 0 and len(locationResults) > currentOffset:
        imageResult = getImage(locationResults[currentOffset]['lat'], locationResults[currentOffset]['lon'], True)
        if imageResult != None:
            text = f"Weather for station {imageResult['weather_station']}. Searched for '{query}'."
            answers.append(
                InlineQueryResultPhoto(
                    id=imageResult['imageId'],
                    photo_url=imageResult['imageLink'],
                    thumb_url=imageResult['thumbLink'],
                    photo_height=imageResult['height'],
                    photo_width=imageResult['width'],
                    description=text,
                    caption=text,
                    title=imageResult['weather_station'],
                )
            )
        else:
            currentOffset += 1

    nextOffset = None
    if len(locationResults) > currentOffset + 1:
        logging.log(msg=f"{queryId} ({query}): requesting: {currentOffset + 1}/{len(locationResults)}", level=20)
        nextOffset = currentOffset + 1
    else:
        logging.log(msg=f"{queryId} ({query}): finished ({len(locationResults)})", level=20)
        if queryId in currentQueryResult:
            del currentQueryResult[queryId]
    context.bot.answer_inline_query(queryId, results=answers, cache_time=60 * 30, next_offset=str(nextOffset))


def debugStuff(update: Update, context: CallbackContext):
    chat_id, message = getStuff(update)
    context.bot.send_message(chat_id, text=f"Answer.")
    logging.log(msg=f"debug", level=20)
    debugTest()


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
dispatcher.add_handler(CommandHandler('debug', debugStuff))
dispatcher.add_handler(MessageHandler(Filters.location, handleLocation))
dispatcher.add_handler(MessageHandler(Filters.text, handleText))
dispatcher.add_handler(InlineQueryHandler(handleInlineQuery))

clearCache()

updater.start_polling()
