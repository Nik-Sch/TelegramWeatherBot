
from telegram.ext import (Updater,
                          CommandHandler,
                          MessageHandler,
                          Filters,
                          CallbackContext,
                          InlineQueryHandler,
                          )
from telegram import (Bot,
                      ReplyKeyboardMarkup,
                      Update,
                      ReplyKeyboardRemove,
                      InlineQueryResult
                      )
import os
import logging
from typing import (Any, Dict, Literal, Optional, Union,
                    List,
                    Tuple,
                    TypedDict,
                    cast
                    )
from telegram.inline.inlinequeryresultphoto import InlineQueryResultPhoto
from telegram.inline.inlinequeryresultmpeg4gif import InlineQueryResultMpeg4Gif
from telegram.message import Message
from db import Backend, Location, StateType, requestsSession
from radar import createRadarAnimation
from weatherProvider import fetchAndPlot, getLocationInfo
import threading
import functools
from threading import Thread
from queue import Queue
from time import sleep
from urllib import parse

CACHING_TIME = 30 * 60

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


class UploadImageResult(TypedDict):
    id: str
    link: str
    thumb: str
    width: int
    height: int


class UploadAnimationResult(TypedDict):
    id: str
    link: str


def start(update: Update, context: CallbackContext):
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text="Send me locations and I will answer with the weather.\nOr you can /add your favorite weather stations for quick weather access.\n\nYou can also mention me with @weatherstuffbot and send weather reports to any chat you like.")


@functools.lru_cache(maxsize=100, typed=False)
def getImage(lat: float, lon: float, tenDays: bool) -> Optional[ImageResult]:
    imageResult = fetchAndPlot(lat, lon, 10 if tenDays else 1.5)
    if imageResult == None:
        return None

    url = "http://image-host/image"
    files = {'image': imageResult['plot'].getvalue()}

    uploadResponse = requestsSession.request("POST", url, files=files)
    uploadJson = cast(UploadImageResult, uploadResponse.json())
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


def clearImageCache():
    logging.log(msg=getImage.cache_info(), level=20)
    logging.log(msg="clearing cache", level=20)
    getImage.cache_clear()
    threading.Timer(CACHING_TIME, clearImageCache).start()


def getRadarAnimation(lat: float, lon: float) -> Tuple[str, str]:
    radar = createRadarAnimation(lat, lon)

    url = "http://image-host/animation"
    files = {'animation': radar.getvalue()}
    uploadResponse = requestsSession.request("POST", url, files=files)
    uploadJson = cast(UploadAnimationResult, uploadResponse.json())
    return (uploadJson['id'], uploadJson['link'])


def sendRadar(chat_id: Union[int, str], bot: Bot, lat: float, lon: float):
    waitingMessage = bot.send_message(chat_id, text="⏳", reply_markup=ReplyKeyboardRemove())
    try:
        _, link = getRadarAnimation(lat, lon)
        if link == None:
            bot.send_message(chat_id, text="Could not create the radar. 😔")
            return
        
        locationText = getLocationName(lat, lon)

        bot.send_animation(chat_id,
                           animation=link,
                           caption=f"Radar for {locationText}",
                           reply_markup=ReplyKeyboardRemove())
    finally:
        bot.delete_message(chat_id=chat_id, message_id=waitingMessage.message_id)


def sendForecast(chat_id: Union[int, str], bot: Bot, lat: float, lon: float, tenDays: bool, name: str = None):
    waitingMessage = bot.send_message(chat_id, text="⏳", reply_markup=ReplyKeyboardRemove())
    try:
        result = getImage(lat, lon, tenDays)
        if result == None:
            bot.send_message(chat_id, text="The location has no weather station nearby.")
            return

        station_text = f"forecast for {name}." if (
            name != None) else f"forecast for {result['weather_station']} ({result['weather_station_distance']}km from location)."
        bot.send_photo(chat_id,
                       photo=result['imageLink'],
                       caption=f"{result['duration']} day {station_text}\nCurrently it is {result['current_temp']}°C and {result['current_str']}.",
                       reply_markup=ReplyKeyboardRemove())
    except Exception as e:
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
    info = getLocationInfo(lat, lon)
    if info == None:
        bot.send_message(chat_id, f"I couldn't find a weather station near the location. 😔")
        return
    name, dist = info
    if db.addLocation(chat_id, {
        'name': name,
        'lat': lat,
        'lon': lon
    }):
        bot.send_message(
            chat_id, f"Station '{name}' ({dist}km from location) added.\nIt will be included in /getall and you can get it individually by '/get {name}'.")
        sendForecast(chat_id, bot, lat, lon, True)
    else:
        bot.send_message(chat_id, f"Station '{name}' is already added.")


def getAll(update: Update, context: CallbackContext):
    chat_id, _ = getStuff(update)
    locations = list(db.getLocations(chat_id))
    if len(locations) == 0:
        context.bot.send_message(
            chat_id, text=f"You need to add a location with /add.")
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


def getWrapper(update: Update, context: CallbackContext, what: StateType):
    chat_id, message = getStuff(update)
    locations = list(db.getLocations(chat_id))
    if len(locations) == 0:
        context.bot.send_message(
            chat_id, text=f"You need to add a location with /add.")
        return

    locationNames = list(map(lambda x: x['name'], locations))
    if context.args != None and len(context.args) == 0:
        db.setState(chat_id, {'type': what})
        message.reply_text(
            'Choose a station.', reply_markup=locationReplyKeyboard(locations))
        return

    if context.args[0] not in locationNames:
        context.bot.send_message(
            chat_id, text=f"You have not added {context.args[0]}.\n You have added {', '.join(locationNames)}.")
        return
    location = next(filter(lambda x: x['name'] == context.args[0], locations), None)
    if what == 'getRadar':
        sendRadar(chat_id, context.bot, location['lat'], location['lon'])
    else:
        sendForecast(chat_id, context.bot,
                     location['lat'], location['lon'], tenDays=what == 'getTenDays', name=location['name'])


def getForecast(update: Update, context: CallbackContext):
    getWrapper(update, context, 'getTenDays')


def getDetailedForecast(update: Update, context: CallbackContext):
    getWrapper(update, context, 'get')


def getRadar(update: Update, context: CallbackContext):
    getWrapper(update, context, 'getRadar')


def delete(update: Update, context: CallbackContext):
    chat_id, message = getStuff(update)
    locations = list(db.getLocations(chat_id))
    if len(locations) == 0:
        context.bot.send_message(
            chat_id, text=f"You need to add a location with /add.")
        return
    db.setState(chat_id, {'type': 'remove'})
    message.reply_text(
        'Which station should be removed?', reply_markup=locationReplyKeyboard(locations))
    return


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
    if 'type' not in state:
        raise ValueError('type is not in state')

    if state['type'] == 'get' or state['type'] == 'getTenDays' or state['type'] == 'getRadar':
        if 'addLocations' in state:
            selectedLocation = next(filter(lambda l: l['name'] == message.text, state['addLocations']), None)
            if selectedLocation != None:
                # type will always be 'get' and send both
                sendRadar(chat_id, context.bot, selectedLocation['lat'], selectedLocation['lon'])
                sendForecast(chat_id, context.bot, selectedLocation['lat'], selectedLocation['lon'], True)
            else:
                context.bot.send_message(chat_id, text="Invalid location selected.", reply_markup=ReplyKeyboardRemove())
            db.setState(chat_id, {'type': 'idle'})
        else:
            locations = db.getLocations(chat_id)
            selectedLocation = next(filter(lambda x: x['name'] == message.text, locations), None)
            if selectedLocation != None:
                if state['type'] == 'getRadar':
                    sendRadar(chat_id, context.bot, selectedLocation['lat'], selectedLocation['lon'])
                else:
                    sendForecast(chat_id, context.bot, selectedLocation['lat'], selectedLocation['lon'], state['type'] == 'getTenDays')
            else:
                context.bot.send_message(
                    chat_id, text="Invalid station name.", reply_markup=ReplyKeyboardRemove())

    elif state['type'] == 'rename':
        locations = db.getLocations(chat_id)

        # new name
        if 'location' in state:
            location = next(filter(lambda x: x['name'] == state['location']['name'], locations), None) # type: ignore
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

    elif state['type'] == 'remove':
        locations = db.getLocations(chat_id)
        location = next(filter(lambda x: x['name'] == message.text, locations), None)
        if location != None:
            db.removeLocation(chat_id, location)
            context.bot.send_message(
                chat_id, text=f"{location['name']} successfully removed.", reply_markup=ReplyKeyboardRemove())
        else:
            context.bot.send_message(
                chat_id, text="Invalid station name.", reply_markup=ReplyKeyboardRemove())

    elif state['type'] == 'add':
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
    elif state['type'] == 'idle' and message.chat.type == 'private':
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
            chat_id, text=f"You need to add a location with /add.")
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
    result = requestsSession.get(f"https://nominatim.openstreetmap.org/search?q={parse.quote(query, safe='')}&format=jsonv2").json()
    return list(map(osmToLocation, result))


def getLocationName(lat: float, lon: float) -> str:
    result = requestsSession.get(f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&zoom=14&format=jsonv2").json()
    res = result['display_name']
    return res


inlineQueues: Dict[str, "Queue[Optional[InlineQueryResult]]"] = {}


def queueImage(lat: float, lon: float, query: str, queryId: str):
    imageResult = getImage(lat, lon, True)
    if imageResult != None:
        logging.info(f"inline queueing {imageResult['imageId']}.")
        text = f"Weather for station {imageResult['weather_station']}. Searched for '{query}'."
        inlineQueues[queryId].put(
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

def queueRadar(lat: float, lon: float, query: str, queryId: str):
    radarId, link = getRadarAnimation(lat, lon)
    locationName = getLocationName(lat, lon)
    logging.info(f"inline queueing radar {radarId}.")
    text = f"Radar for {locationName}. Searched for '{query}'."
    inlineQueues[queryId].put(
        InlineQueryResultMpeg4Gif(
            id=radarId,
            mpeg4_url=link,
            thumb_url=link,
            mpeg4_height=512,
            mpeg4_width=512,
            description=text,
            caption=text,
            title=locationName,
        )
    )


def provideImagesForQuery(query: str, queryId: str):
    locations = queryLocations(query)
    for location in locations:
        queueRadar(location['lat'], location['lon'], query, queryId)
        queueImage(location['lat'], location['lon'], query, queryId)
    logging.info('inline queuing None, finished.')
    inlineQueues[queryId].put(None)
    sleep(5)
    logging.info(f"inline deleting queue {queryId}")
    del inlineQueues[queryId]



def handleInlineQuery(update: Update, context: CallbackContext):
    query: str = update.inline_query.query
    queryId: str = update.inline_query.id
    offset: str = update.inline_query.offset
    firstQueryId: str = ''
    counter: str = '0'
    logging.info(f"offset: {offset}")
    if offset == '':
        # first call for current query
        logging.info(f"creating queue {queryId}")
        firstQueryId = queryId
        inlineQueues[firstQueryId] = Queue()
        thread = Thread(target=provideImagesForQuery, args=(query, firstQueryId))
        thread.start()
    else:
        firstQueryId, counter = offset.split('-')

    answers: List[InlineQueryResult] = []

    if firstQueryId in inlineQueues:
        nextItem = inlineQueues[firstQueryId].get()
        if nextItem != None:
            logging.info(f"inline got {nextItem.id}")
            answers.append(nextItem)

    logging.info(f"inline sending {len(answers)} items, counter = {counter}")
    context.bot.answer_inline_query(queryId, results=answers, cache_time=CACHING_TIME, next_offset=f"{firstQueryId}-{int(counter) + 1}")


def handleError(update: Update, context: CallbackContext):
    logging.error(context.error, exc_info=True)
    try:
        context.bot.send_message(update.effective_chat.id, text="Uh oh, something went wrong.\nIf you like you can tell @NikSch.")
    except:
        pass


updater = Updater(token=os.environ.get('BOT_TOKEN'))
dispatcher = updater.dispatcher

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(CommandHandler('add', add))
dispatcher.add_handler(CommandHandler('getAll', getAll))
dispatcher.add_handler(CommandHandler('get', getForecast))
dispatcher.add_handler(CommandHandler('getDetailed', getDetailedForecast))
dispatcher.add_handler(CommandHandler('radar', getRadar))
dispatcher.add_handler(CommandHandler('rename', rename))
dispatcher.add_handler(CommandHandler('delete', delete))
dispatcher.add_handler(CommandHandler('remove', delete))
dispatcher.add_handler(MessageHandler(Filters.location, handleLocation))
dispatcher.add_handler(MessageHandler(Filters.text, handleText))
dispatcher.add_handler(InlineQueryHandler(handleInlineQuery))
dispatcher.add_error_handler(handleError)

clearImageCache()

updater.start_polling()
