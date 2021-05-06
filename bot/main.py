
from queue import Empty
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
from backend import Backend, Location, StateType, getRequestsCache
from radar import Radar
from weatherProvider import WeatherProvider
import threading
import functools
from threading import Thread
from multiprocessing import Queue, Pool
from time import sleep
from urllib import parse
from dataclasses import dataclass

CACHING_TIME = 10 * 60

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

@dataclass
class QueryParameter:
    location: Location
    query: str


def getLocationName(lat: float, lon: float) -> str:
    result = getRequestsCache().get(f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&zoom=14&format=jsonv2").json()
    res = result['display_name']
    return res

@functools.lru_cache(typed=False)
def getImage(lat: float, lon: float, tenDays: bool) -> Optional[ImageResult]:

    imageResult = WeatherProvider().fetchAndPlot(lat, lon, 10 if tenDays else 1.5)
    if imageResult == None:
        return None

    url = "http://image-host/image"
    files = {'image': imageResult['plot'].getvalue()}

    uploadResponse = getRequestsCache().request("POST", url, files=files)
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


@functools.lru_cache(typed=False)
def getRadarAnimation(lat: float, lon: float) -> Tuple[str, str]:
    radarIO = Radar().createRadarAnimation(lat, lon)

    url = "http://image-host/animation"
    files = {'animation': radarIO.getvalue()}
    uploadResponse = getRequestsCache().request("POST", url, files=files)
    uploadJson = cast(UploadAnimationResult, uploadResponse.json())
    return (uploadJson['id'], uploadJson['link'])


def clearImageCache():
    logging.log(msg=getImage.cache_info(), level=20)
    logging.log(msg="clearing lru caches", level=20)
    getImage.cache_clear()
    getRadarAnimation.cache_clear()
    threading.Timer(CACHING_TIME, clearImageCache).start()
@dataclass
class QueueElement:
    type: Literal['photo', 'animation']
    id: str
    url: str
    thumb_url: str
    height: int
    width: int
    text: str
    title: str


def queueImage(param: QueryParameter):
    imageResult = getImage(param.location['lat'], param.location['lon'], True)
    if imageResult != None:
        logging.info(f"inline queueing {imageResult['imageId']}.")
        text = f"Weather for station {imageResult['weather_station']}. Searched for '{param.query}'."
        createResults.queue.put(
            QueueElement(
                type='photo',
                id=imageResult['imageId'],
                url=imageResult['imageLink'],
                thumb_url=imageResult['thumbLink'],
                height=imageResult['height'],
                width=imageResult['width'],
                text=text,
                title=imageResult['weather_station'],
            )
        )


def queueRadar(param: QueryParameter):
    radarId, link = getRadarAnimation(param.location['lat'], param.location['lon'])
    locationName = getLocationName(param.location['lat'], param.location['lon'])
    logging.info(f"inline queueing radar {radarId}.")
    text = f"Radar for {locationName}. Searched for '{param.query}'."
    createResults.queue.put(
        QueueElement(
            type='animation',
            id=radarId,
            url=link,
            thumb_url=link,
            height=512,
            width=512,
            text=text,
            title=locationName,
        )
    )


def createResults(param: QueryParameter):
    threads = [Thread(target=queueRadar, args=[param]),
               Thread(target=queueImage, args=[param])]
    for t in threads:
        t.setDaemon(True)
        t.start()
    for t in threads:
        t.join()

def inlineInit(q: Queue):
    logging.warning(f'init inline {os.getpid()}')
    createResults.queue = q

class MainBot:
    db: Backend
    weatherProvider: WeatherProvider
    radar: Radar

    def __init__(self, db: Backend) -> None:
        self.db = db

    def start(self, update: Update, context: CallbackContext):
        context.bot.send_message(chat_id=update.effective_chat.id,
                                text="Send me locations and I will answer with the weather.\nOr you can /add your favorite weather stations for quick weather access.\n\nYou can also mention me with @weatherstuffbot and send weather reports to any chat you like.")


    def sendRadar(self, chat_id: Union[int, str], bot: Bot, lat: float, lon: float):
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

    def sendForecast(self, chat_id: Union[int, str], bot: Bot, lat: float, lon: float, tenDays: bool, name: str = None):
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
        finally:
            bot.delete_message(chat_id=chat_id, message_id=waitingMessage.message_id)

    def getStuff(self, update: Update) -> Tuple[str, Message]:
        message = None
        if update.edited_message:
            message = update.edited_message
        else:
            message = update.message
        return (update.effective_chat.id, message)

    def addLocation(self, chat_id: str, bot: Bot, lat: float, lon: float):
        info = self.weatherProvider.getLocationInfo(lat, lon)
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
            self.sendForecast(chat_id, bot, lat, lon, True)
        else:
            bot.send_message(chat_id, f"Station '{name}' is already added.")

    def getAll(self, update: Update, context: CallbackContext):
        chat_id, _ = self.getStuff(update)
        locations = list(db.getLocations(chat_id))
        if len(locations) == 0:
            context.bot.send_message(
                chat_id, text=f"You need to add a location with /add.")
            return

        for location in locations:
            self.sendForecast(chat_id, context.bot,
                        location['lat'], location['lon'], True, name=location['name'])

    def locationReplyKeyboard(self, locations: List[Location]) -> ReplyKeyboardMarkup:
        locationNames = list(map(lambda x: x['name'], locations))

        keyboard = []
        i = 0
        while i < len(locationNames) - 1:
            keyboard.append([locationNames[i], locationNames[i + 1]])
            i += 2

        if len(locationNames) - i == 1:
            keyboard.append([locationNames[i]])
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    def getWrapper(self, update: Update, context: CallbackContext, what: StateType):
        chat_id, message = self.getStuff(update)
        locations = list(db.getLocations(chat_id))
        if len(locations) == 0:
            context.bot.send_message(
                chat_id, text=f"You need to add a location with /add.")
            return

        locationNames = list(map(lambda x: x['name'], locations))
        if context.args != None and len(context.args) == 0:
            db.setState(chat_id, {'type': what})
            message.reply_text(
                'Choose a station.', reply_markup=self.locationReplyKeyboard(locations))
            return

        if context.args[0] not in locationNames:
            context.bot.send_message(
                chat_id, text=f"You have not added {context.args[0]}.\n You have added {', '.join(locationNames)}.")
            return
        location = next(filter(lambda x: x['name'] == context.args[0], locations), None)
        if what == 'getRadar':
            self.sendRadar(chat_id, context.bot, location['lat'], location['lon'])
        else:
            self.sendForecast(chat_id, context.bot,
                        location['lat'], location['lon'], tenDays=what == 'getTenDays', name=location['name'])

    def getForecast(self, update: Update, context: CallbackContext):
        self.getWrapper(update, context, 'getTenDays')

    def getDetailedForecast(self, update: Update, context: CallbackContext):
        self.getWrapper(update, context, 'get')

    def getRadar(self, update: Update, context: CallbackContext):
        self.getWrapper(update, context, 'getRadar')

    def delete(self, update: Update, context: CallbackContext):
        chat_id, message = self.getStuff(update)
        locations = list(db.getLocations(chat_id))
        if len(locations) == 0:
            context.bot.send_message(
                chat_id, text=f"You need to add a location with /add.")
            return
        db.setState(chat_id, {'type': 'remove'})
        message.reply_text(
            'Which station should be removed?', reply_markup=self.locationReplyKeyboard(locations))
        return

    def handleLocation(self, update: Update, context: CallbackContext):
        chat_id, message = self.getStuff(update)
        lat = message.location.latitude
        lon = message.location.longitude
        if db.getState(chat_id)['type'] == 'add':  # type: ignore
            self.addLocation(chat_id, context.bot, lat, lon)
            db.setState(chat_id, {'type': 'idle'})
        else:
            self.sendForecast(chat_id, context.bot, lat, lon, True)

    def add(self, update: Update, context: CallbackContext):
        chat_id, _ = self.getStuff(update)
        db.setState(chat_id, {'type': 'add'})
        context.bot.send_message(chat_id, text="Ok, now send a location.")

    def handleText(self, update: Update, context: CallbackContext):
        chat_id, message = self.getStuff(update)
        state = db.getState(chat_id)
        db.setState(chat_id, {'type': 'idle'})
        if 'type' not in state:
            raise ValueError('type is not in state')

        if state['type'] == 'get' or state['type'] == 'getTenDays' or state['type'] == 'getRadar':
            if 'addLocations' in state:
                selectedLocation = next(filter(lambda l: l['name'] == message.text, state['addLocations']), None)
                if selectedLocation != None:
                    # type will always be 'get' and send both
                    self.sendRadar(chat_id, context.bot, selectedLocation['lat'], selectedLocation['lon'])
                    self.sendForecast(chat_id, context.bot, selectedLocation['lat'], selectedLocation['lon'], True)
                else:
                    context.bot.send_message(chat_id, text="Invalid location selected.", reply_markup=ReplyKeyboardRemove())
                db.setState(chat_id, {'type': 'idle'})
            else:
                locations = db.getLocations(chat_id)
                selectedLocation = next(filter(lambda x: x['name'] == message.text, locations), None)
                if selectedLocation != None:
                    if state['type'] == 'getRadar':
                        self.sendRadar(chat_id, context.bot, selectedLocation['lat'], selectedLocation['lon'])
                    else:
                        self.sendForecast(chat_id, context.bot, selectedLocation['lat'], selectedLocation['lon'], state['type'] == 'getTenDays')
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
                    self.addLocation(chat_id, context.bot, selectedLocation['lat'], selectedLocation['lon'])
                else:
                    context.bot.send_message(chat_id, text="Invalid location selected.", reply_markup=ReplyKeyboardRemove())
                db.setState(chat_id, {'type': 'idle'})
            else:
                addLocations = self.queryLocations(message.text)
                if len(addLocations) > 0:
                    db.setState(chat_id, {
                        'type': 'add',
                        'addLocations': addLocations
                    })
                    context.bot.send_message(chat_id,
                                            text="I have found these locations matching. Choose one:",
                                            reply_markup=self.locationReplyKeyboard(addLocations))
                else:
                    context.bot.send_message(chat_id,
                                            text="I couldn't find a location.",
                                            reply_markup=ReplyKeyboardRemove())
        elif state['type'] == 'idle' and message.chat.type == 'private':
            addLocations = self.queryLocations(message.text)
            if len(addLocations) > 0:
                db.setState(chat_id, {
                    'type': 'get',
                    'addLocations': addLocations
                })
                context.bot.send_message(chat_id,
                                        text="I have found these locations matching. Choose one:",
                                         reply_markup=self.locationReplyKeyboard(addLocations))
            else:
                context.bot.send_message(chat_id,
                                        text="I couldn't find a location.",
                                        reply_markup=ReplyKeyboardRemove())

    def rename(self, update: Update, context: CallbackContext):
        chat_id, message = self.getStuff(update)
        db.setState(chat_id, {'type': 'rename'})

        locations = list(db.getLocations(chat_id))
        if len(locations) == 0:
            context.bot.send_message(
                chat_id, text=f"You need to add a location with /add.")
            return

        message.reply_text(
            'Choose a station to rename.', reply_markup=self.locationReplyKeyboard(locations))

    def osmToLocation(self, element: Any) -> Location:
        return {
            'lat': element['lat'],
            'lon': element['lon'],
            'name': element['display_name']
        }

    def queryLocations(self, query: str) -> List[Location]:
        result = db.requestsSession.get(f"https://nominatim.openstreetmap.org/search?q={parse.quote(query, safe='')}&format=jsonv2").json()
        return list(map(self.osmToLocation, result))


    inlineQueues: Dict[str, "Queue[Optional[QueueElement]]"] = {}

    def provideImagesForQuery(self, query: str, queryId: str):
        POOL_SIZE = 4

        locations = self.queryLocations(query)
        params = map(lambda loc: QueryParameter(loc, query), locations)
        with Pool(POOL_SIZE, inlineInit, [self.inlineQueues[queryId]]) as pool:
            pool.map(createResults, params, int(len(locations) / POOL_SIZE))

        logging.info('inline queuing None, finished.')
        self.inlineQueues[queryId].put(None)
        sleep(5)
        logging.info(f"inline deleting queue {queryId}")
        del self.inlineQueues[queryId]

    def queueElementToResult(self, elem: QueueElement) -> InlineQueryResult:
        if elem.type == 'photo':
            return InlineQueryResultPhoto(
                id=elem.id,
                photo_url=elem.url,
                thumb_url=elem.thumb_url,
                photo_height=elem.height,
                photo_width=elem.width,
                description=elem.text,
                caption=elem.text,
                title=elem.title,
            )
        else:
            return InlineQueryResultMpeg4Gif(
                id=elem.id,
                mpeg4_url=elem.url,
                thumb_url=elem.thumb_url,
                mpeg4_height=elem.height,
                mpeg4_width=elem.width,
                description=elem.text,
                caption=elem.text,
                title=elem.title,
            )


    def handleInlineQuery(self, update: Update, context: CallbackContext):
        query: str = update.inline_query.query
        queryId: str = update.inline_query.id
        offset: str = update.inline_query.offset
        firstQueryId: str = ''
        counter: str = '0'
        if offset == '':
            # first call for current query
            logging.info(f"creating queue {queryId}")
            firstQueryId = queryId
            self.inlineQueues[firstQueryId] = Queue()
            thread = Thread(target=self.provideImagesForQuery, args=(query, firstQueryId))
            thread.start()
        else:
            firstQueryId, counter = offset.split('-')

        answers: List[InlineQueryResult] = []

        if firstQueryId in self.inlineQueues:
            nextItem = self.inlineQueues[firstQueryId].get()
            while nextItem != None:
                answers.append(self.queueElementToResult(nextItem))
                try:
                    nextItem = self.inlineQueues[firstQueryId].get(timeout=0.5)
                except Empty:
                    nextItem = None
        logging.info(f'*** inline sending {len(answers)} items')
        update.inline_query.answer(answers, cache_time=CACHING_TIME, next_offset=f"{firstQueryId}-{int(counter) + 1}")

    def handleError(self, update: Update, context: CallbackContext):
        logging.error(context.error, exc_info=True)
        try:
            context.bot.send_message(update.effective_chat.id, text="Uh oh, something went wrong.\nIf you like you can tell @NikSch.")
        except:
            pass

if __name__ == '__main__':
    db = Backend()
    bot = MainBot(db)

    updater = Updater(token=os.environ.get('BOT_TOKEN'))
    dispatcher = updater.dispatcher

    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        level=logging.INFO)
    dispatcher.add_handler(CommandHandler('start', bot.start))
    dispatcher.add_handler(CommandHandler('add', bot.add))
    dispatcher.add_handler(CommandHandler('getAll', bot.getAll))
    dispatcher.add_handler(CommandHandler('get', bot.getForecast))
    dispatcher.add_handler(CommandHandler('getDetailed', bot.getDetailedForecast))
    dispatcher.add_handler(CommandHandler('radar', bot.getRadar))
    dispatcher.add_handler(CommandHandler('rename', bot.rename))
    dispatcher.add_handler(CommandHandler('delete', bot.delete))
    dispatcher.add_handler(CommandHandler('remove', bot.delete))
    dispatcher.add_handler(MessageHandler(Filters.location, bot.handleLocation))
    dispatcher.add_handler(MessageHandler(Filters.text, bot.handleText))
    dispatcher.add_handler(InlineQueryHandler(bot.handleInlineQuery))
    dispatcher.add_error_handler(bot.handleError)

    clearImageCache()

    updater.start_polling()
