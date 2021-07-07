
import json
from queue import Empty
import time
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
                      InlineQueryResult,
                      InputMedia
                      )
import os
import logging
from typing import (Any, ContextManager, Dict, Literal, Optional, Union,
                    List,
                    Tuple,
                    TypedDict,
                    cast
                    )
from telegram.files.inputmedia import InputMediaAnimation, InputMediaDocument, InputMediaPhoto, InputMediaVideo
from telegram.inline.inlinequeryresultphoto import InlineQueryResultPhoto
from telegram.inline.inlinequeryresultmpeg4gif import InlineQueryResultMpeg4Gif
from telegram.message import Message
from telegram.utils.types import JSONDict
from backend import Backend, Location, State, StateType, getRequestsCache
from radar import Radar, printTime
from weatherProvider import WeatherProvider
import threading
import functools
from threading import Thread
from multiprocessing import Queue, Pool, pool
from time import sleep
from urllib import parse
from dataclasses import dataclass
import concurrent.futures

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


QueryType = Literal['plot', 'plotTenDays', 'radar']


@dataclass
class QueryParameter:
    location: Location
    query: Optional[str]
    type: QueryType


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
    logging.info("clearing lru caches")
    logging.info(getImage.cache_info())
    logging.info(getRadarAnimation.cache_info())
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
    current_temp: Optional[float]


def queueImage(param: QueryParameter):
    imageResult = getImage(param.location.lat, param.location.lon, param.type == 'plotTenDays')
    if imageResult != None:
        logging.info(f"queueing {imageResult['imageId']}.")
        if param.query == None:
            text = f"Weather for station {imageResult['weather_station']}."
        else:
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
                current_temp=imageResult['current_temp']
            )
        )


def queueRadar(param: QueryParameter):
    radarId, link = getRadarAnimation(param.location.lat, param.location.lon)
    locationName = getLocationName(param.location.lat, param.location.lon)
    logging.info(f"queueing radar {radarId}.")
    if param.query == None:
        text = f"Radar for {locationName}."
    else:
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
            current_temp=None
        )
    )


def createResults(param: QueryParameter):
    if param.type == 'plot' or param.type == 'plotTenDays':
        queueImage(param)
    else:
        queueRadar(param)


def setQueueForProcess(q: Queue):
    createResults.queue = q


class MainBot:
    db: Backend

    inlineQueues: Dict[str, "Queue[Optional[QueueElement]]"] = {}
    inlineSentResultIds: Dict[str, List[str]] = {}
    inlinePools: Dict[str, pool.Pool] = {}
    activeInlineUsers: Dict[int, str] = {}

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

    def addLocation(self, chat_id: str, context: CallbackContext, lat: float, lon: float):
        info = WeatherProvider().getLocationInfo(lat, lon)
        if info == None:
            context.bot.send_message(chat_id, f"I couldn't find a weather station near the location. 😔")
            return
        name, dist = info
        if db.addLocation(chat_id, Location(lat, lon, name)):
            context.bot.send_message(
                chat_id, f"Station '{name}' ({dist}km from location) added.\nIt will be included in /getall and you can get it individually by '/get {name}'.")
            self.sendAllForLocation(context, chat_id, Location(lat, lon, name))
        else:
            context.bot.send_message(chat_id, f"Station '{name}' is already added.")

    def sendAllForLocation(self, context: CallbackContext, chat_id: str, location: Location):
        waitingMessage = context.bot.send_message(chat_id, text="⏳", reply_markup=ReplyKeyboardRemove())
        try:
            album: List[InputMedia] = []
            params = map(lambda t: QueryParameter(location, None, t), ['plot', 'plotTenDays', 'radar'])  # type: ignore
            queue: Queue[QueueElement] = Queue()
            with Pool(3, setQueueForProcess, [queue]) as pool:
                pool.map(createResults, params)

            first = True
            while not queue.empty():
                elem = queue.get_nowait()
                logging.info(f"dequeue {elem.type}: {elem}")
                if elem.type == 'photo':
                    if first:
                        album.append(InputMediaPhoto(elem.url, caption=f"Weather for {location.name}. ({elem.current_temp}°C currently)"))
                        first = False
                    else:
                        album.append(InputMediaPhoto(elem.url))
                else:
                    context.bot.send_animation(chat_id, animation=elem.url, caption=f"Radar for {location.name}.")
            context.bot.send_media_group(chat_id, album)
        finally:
            context.bot.delete_message(chat_id=chat_id, message_id=waitingMessage.message_id)

    def getAll(self, update: Update, context: CallbackContext):
        chat_id, _ = self.getStuff(update)
        locations = list(db.getLocations(chat_id))
        if len(locations) == 0:
            context.bot.send_message(
                chat_id, text=f"You need to add a location with /add.")
            return

        for location in locations:
            self.sendAllForLocation(context, chat_id, location)

    def setDefault(self, update: Update, context: CallbackContext):
        chat_id, message =  self.getStuff(update)
        locations = list(self.db.getLocations(chat_id))
        self.db.setState(chat_id, State('set_default'))
        message.reply_text("Which location should be the new default location?", reply_markup=self.locationReplyKeyboard(locations))

    def getDefault(self, update: Update, context: CallbackContext):
        chat_id, message =  self.getStuff(update)
        location = self.db.getDefaultLocation(chat_id)
        if location == None:
            message.reply_text("You need to set a default location with /setdefault.")
            return
        self.sendAllForLocation(context, chat_id, location)

    def locationReplyKeyboard(self, locations: List[Location]) -> ReplyKeyboardMarkup:
        locationNames = list(map(lambda x: x.name, locations))

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
        
        if len(locations) == 1:
            location = locations[0]
            if what == 'getRadar':
                self.sendRadar(chat_id, context.bot, location.lat, location.lon)
            else:
                self.sendForecast(chat_id, context.bot,
                                location.lat, location.lon, tenDays=what == 'getTenDays', name=location.name)
            return

        locationNames = list(map(lambda x: x.name, locations))
        if context.args != None and len(context.args) == 0:
            db.setState(chat_id, State(what))
            message.reply_text(
                'Choose a station.', reply_markup=self.locationReplyKeyboard(locations))
            return

        if context.args[0] not in locationNames:
            context.bot.send_message(
                chat_id, text=f"You have not added {context.args[0]}.\n You have added {', '.join(locationNames)}.")
            return
        location = next(filter(lambda x: x.name == context.args[0], locations), None)
        if what == 'getRadar':
            self.sendRadar(chat_id, context.bot, location.lat, location.lon)
        else:
            self.sendForecast(chat_id, context.bot,
                              location.lat, location.lon, tenDays=what == 'getTenDays', name=location.name)

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
        db.setState(chat_id, State('remove'))
        message.reply_text(
            'Which station should be removed?', reply_markup=self.locationReplyKeyboard(locations))
        return

    def handleLocation(self, update: Update, context: CallbackContext):
        chat_id, message = self.getStuff(update)
        lat = message.location.latitude
        lon = message.location.longitude
        if db.getState(chat_id)['type'] == 'add':  # type: ignore
            self.addLocation(chat_id, context, lat, lon)
            db.setState(chat_id, State('idle'))
        else:
            location = Location(lat, lon, getLocationName(lat, lon))
            self.sendAllForLocation(context, chat_id, location)

    def add(self, update: Update, context: CallbackContext):
        chat_id, _ = self.getStuff(update)
        db.setState(chat_id, State('add'))
        context.bot.send_message(chat_id, text="Ok, now send a location.")

    def handleText(self, update: Update, context: CallbackContext):
        chat_id, message = self.getStuff(update)
        state = db.getState(chat_id)
        db.setState(chat_id, State('idle'))

        if state.type == 'get' or state.type == 'getTenDays' or state.type == 'getRadar':
            if state.addLocations is not None:
                logging.info(message.text)
                logging.info(state.addLocations)
                selectedLocation = next(filter(lambda l: l.name == message.text, state.addLocations), None)
                if selectedLocation != None:
                    self.sendAllForLocation(context, chat_id, selectedLocation)
                else:
                    context.bot.send_message(chat_id, text="Invalid location selected.", reply_markup=ReplyKeyboardRemove())
                db.setState(chat_id, State('idle'))
            else:
                locations = db.getLocations(chat_id)
                selectedLocation = next(filter(lambda x: x.name == message.text, locations), None)
                if selectedLocation != None:
                    if state.type == 'getRadar':
                        self.sendRadar(chat_id, context.bot, selectedLocation.lat, selectedLocation.lon)
                    else:
                        self.sendForecast(chat_id, context.bot, selectedLocation.lat, selectedLocation.lon, state.type == 'getTenDays')
                else:
                    context.bot.send_message(
                        chat_id, text="Invalid station name.", reply_markup=ReplyKeyboardRemove())

        elif state.type == 'rename':
            locations = db.getLocations(chat_id)

            # new name
            if state.location is not None:
                location = next(filter(lambda x: x.name == state.location.name, locations), None)  # type: ignore
                if location != None:
                    db.renameLocation(chat_id, location, message.text)
                    context.bot.send_message(
                        chat_id, f"'{state.location.name}' was renamed to '{message.text}'")
                else:
                    context.bot.send_message(
                        chat_id, text="Invalid station name.", reply_markup=ReplyKeyboardRemove())
                return

            location = next(
                filter(lambda x: x.name == message.text, locations), None)
            if location != None:
                db.setState(chat_id, State('rename', location=location))
                context.bot.send_message(
                    chat_id, text="Ok. What is the new name?", reply_markup=ReplyKeyboardRemove())
            else:
                context.bot.send_message(
                    chat_id, text="Invalid station name.", reply_markup=ReplyKeyboardRemove())

        elif state.type == 'remove':
            locations = db.getLocations(chat_id)
            location = next(filter(lambda x: x.name == message.text, locations), None)
            if location != None:
                db.removeLocation(chat_id, location)
                context.bot.send_message(
                    chat_id, text=f"{location.name} successfully removed.", reply_markup=ReplyKeyboardRemove())
            else:
                context.bot.send_message(
                    chat_id, text="Invalid station name.", reply_markup=ReplyKeyboardRemove())

        elif state.type == 'add':
            if state.addLocations is not None:
                selectedLocation = next(filter(lambda l: l.name == message.text, state.addLocations), None)
                if selectedLocation != None:
                    self.addLocation(chat_id, context, selectedLocation.lat, selectedLocation.lon)
                else:
                    context.bot.send_message(chat_id, text="Invalid location selected.", reply_markup=ReplyKeyboardRemove())
                db.setState(chat_id, State('idle'))
            else:
                addLocations = self.queryLocations(message.text)
                if len(addLocations) > 0:
                    db.setState(chat_id, State('add', addLocations=addLocations))
                    context.bot.send_message(chat_id,
                                             text="I have found these locations matching. Choose one:",
                                             reply_markup=self.locationReplyKeyboard(addLocations))
                else:
                    context.bot.send_message(chat_id,
                                             text="I couldn't find a location.",
                                             reply_markup=ReplyKeyboardRemove())
        elif state.type == 'idle' and message.chat.type == 'private':
            addLocations = self.queryLocations(message.text)
            if len(addLocations) > 0:
                db.setState(chat_id, State('get', addLocations=addLocations))
                context.bot.send_message(chat_id,
                                         text="I have found these locations matching. Choose one:",
                                         reply_markup=self.locationReplyKeyboard(addLocations))
            else:
                context.bot.send_message(chat_id,
                                         text="I couldn't find a location.",
                                         reply_markup=ReplyKeyboardRemove())
        elif state.type == 'set_default':
            locations = db.getLocations(chat_id)
            selectedLocation = next(filter(lambda x: x.name == message.text, locations), None)
            if selectedLocation != None:
                self.db.setDefaultLocation(chat_id, selectedLocation)
                message.reply_text(
                    f"Updated the default location to {selectedLocation.name}", reply_markup=ReplyKeyboardRemove())
            else:
                context.bot.send_message(
                    chat_id, text="Invalid station name.", reply_markup=ReplyKeyboardRemove())

    def rename(self, update: Update, context: CallbackContext):
        chat_id, message = self.getStuff(update)
        db.setState(chat_id, State('rename'))

        locations = list(db.getLocations(chat_id))
        if len(locations) == 0:
            context.bot.send_message(
                chat_id, text=f"You need to add a location with /add.")
            return

        message.reply_text(
            'Choose a station to rename.', reply_markup=self.locationReplyKeyboard(locations))

    def osmToLocation(self, element: Any) -> Location:
        return Location(element['lat'], element['lon'], element['display_name'])

    def queryLocations(self, query: str) -> List[Location]:
        result = db.requestsSession.get(f"https://nominatim.openstreetmap.org/search?q={parse.quote(query, safe='')}&format=jsonv2").json()
        return list(map(self.osmToLocation, result))

    def provideImagesForQuery(self, query: str, queryId: str):
        location = self.queryLocations(query)[0]
        types: List[QueryType] = ['plot', 'plotTenDays', 'radar']
        params = map(lambda t: QueryParameter(location, query, t), types)  # type: ignore
        with Pool(3, setQueueForProcess, [self.inlineQueues[queryId]]) as pool:
            self.inlinePools[queryId] = pool
            pool.map(createResults, params)
            del self.inlinePools[queryId]

        logging.info('inline queuing None, finished.')
        self.inlineQueues[queryId].put(None)
        sleep(5)
        logging.info(f"inline deleting queue {queryId}")
        if queryId in self.inlineQueues:
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

    def stopQuery(self, qid: str):
        logging.info(f'stopping {qid}')
        if qid in self.inlineSentResultIds:
            del self.inlineSentResultIds[qid]
        if qid in self.inlinePools:
            self.inlinePools[qid].terminate()
            del self.inlinePools[qid]
        if qid in self.inlineQueues:
            del self.inlineQueues[qid]

    def handleInlineQuery(self, update: Update, context: CallbackContext):
        query: str = update.inline_query.query
        queryId: str = update.inline_query.id
        offset: str = update.inline_query.offset
        userId: int = update.inline_query.from_user.id
        firstQueryId: str = ''
        counter: str = '0'
        # logging.info(f"""
        # -----------------------------------
        # '{offset}':
        # pools: {list(self.inlinePools.keys())}
        # queues: {list(self.inlineQueues.keys())}
        # users: {list(self.activeInlineUsers.keys())}
        # """)

        if offset == '':
            # first call for current query
            if userId in self.activeInlineUsers:
                oldQueryId = self.activeInlineUsers[userId]
                logging.info(f'terminating {oldQueryId} because user has a new query')
                self.stopQuery(oldQueryId)

            firstQueryId = queryId
            self.activeInlineUsers[userId] = firstQueryId
            self.inlineQueues[firstQueryId] = Queue()
            self.inlineSentResultIds[firstQueryId] = []
            thread = Thread(target=self.provideImagesForQuery, args=(query, firstQueryId))
            thread.start()
        else:
            firstQueryId, counter = offset.split('-')

        answers: List[InlineQueryResult] = []

        if firstQueryId in self.inlineQueues:
            # be sure to get at least one valid item
            try:
                nextItem = self.inlineQueues[firstQueryId].get(timeout=15)
                while nextItem != None and nextItem.id in self.inlineSentResultIds[firstQueryId]:
                    nextItem = self.inlineQueues[firstQueryId].get(timeout=15)
            except Empty:
                logging.info("15s timeout while waiting for inline")
                nextItem = None

            # while nextItem is not None (end of queue), add it and try to get more items
            while nextItem != None:
                if nextItem.id not in self.inlineSentResultIds[firstQueryId]:
                    self.inlineSentResultIds[firstQueryId].append(nextItem.id)
                    answers.append(self.queueElementToResult(nextItem))
                try:
                    nextItem = self.inlineQueues[firstQueryId].get(timeout=0.5)
                except Empty:
                    nextItem = None

        if len(answers) == 0:
            self.stopQuery(firstQueryId)

        logging.info(f'*** inline sending {len(answers)} items')
        try:
            update.inline_query.answer(answers, cache_time=10, next_offset=f"{firstQueryId}-{int(counter) + 1}")
        except BaseException as e:
            logging.error(e, exc_info=True)
            if userId in self.activeInlineUsers and self.activeInlineUsers[userId] == firstQueryId:
                logging.info(f'terminating {firstQueryId}')
                self.stopQuery(firstQueryId)

    def handleError(self, update: Update, context: CallbackContext):
        logging.exception(context.error, exc_info=True)
        try:
            context.bot.send_message(update.effective_chat.id, text="Uh oh, something went wrong.\nIf you like you can tell @NikSch.")
        except:
            pass


if __name__ == '__main__':
    db = Backend()
    bot = MainBot(db)

    TOKEN = os.environ.get('BOT_TOKEN')
    if TOKEN == None:
        raise TypeError('No bot token defined')
    HOSTNAME = os.environ.get('BOT_URL')
    if HOSTNAME == None:
        raise TypeError('No bot url defined')

    updater = Updater(token=TOKEN, workers=8)
    dispatcher = updater.dispatcher

    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        level=logging.INFO)

    commands = [
        ['start', bot.start, 'Send the description text'],
        ['add', bot.add, 'Add a new weather station'],
        ['getall', bot.getAll, 'get the full forecast for all locations you added'],
        ['get', bot.getForecast, 'get the full forecast for a location'],
        ['getdetailed', bot.getDetailedForecast, 'get a detailed forecast for a location for the next day'],
        ['getdefault', bot.getDefault, 'get the full forecast for the default location'],
        ['setdefault', bot.setDefault, 'set the default location'],
        ['radar', bot.getRadar, 'get a rain radar'],
        ['rename', bot.rename, 'rename a weather station'],
        ['delete', bot.delete, 'delete a station'],
        ['remove', bot.delete, 'delete a station'],
    ]
    for name, fun, _ in commands:
        dispatcher.add_handler(CommandHandler(name, fun, run_async=True))
    dispatcher.add_handler(MessageHandler(Filters.location, bot.handleLocation, run_async=True))
    dispatcher.add_handler(MessageHandler(Filters.text, bot.handleText, run_async=True))
    dispatcher.add_handler(InlineQueryHandler(bot.handleInlineQuery, run_async=True))
    dispatcher.add_error_handler(bot.handleError)
    updater.bot.set_my_commands([(name, desc) for name, _, desc in commands])

    clearImageCache()

    updater.start_polling()
