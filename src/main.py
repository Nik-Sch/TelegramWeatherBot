from telegram.ext import (Updater,
                          CommandHandler,
                          MessageHandler,
                          Filters,
                          CallbackContext,
                          CallbackQueryHandler,
                          )
from telegram import (Bot,
                      InlineKeyboardMarkup,
                      InlineKeyboardButton,
                      Update, chat,
                      )
import redis
import os
import logging
import urllib.request
import json
from datetime import datetime, timedelta
from matplotlib import pyplot as plt
from matplotlib.dates import (date2num,
                              DateFormatter,
                              DayLocator,
                              )
import tempfile
from typing import (Union,
                    List,
                    Tuple
                    )
# import numpy as np

redisDB = redis.Redis(host='redis', port=6379)
chatIdsAddingLocations: List[Union[int, str]] = []


def fetchWeather(lat: float, lon: float, duration: float):
    today = datetime.now().isoformat()
    lastday = (datetime.now() + timedelta(days=duration)).isoformat()
    forecast = []
    with urllib.request.urlopen(f"https://api.brightsky.dev/weather?lat={lat}&lon={lon}&date={today}&last_date={lastday}") as url:
        forecast = json.loads(url.read().decode())
    weather_station = forecast['sources'][0]['station_name']
    weather_station_distance = forecast['sources'][0]['distance']
    dates = []
    temps = []
    precs = []
    suns = []
    for element in forecast['weather']:
        dates.append(datetime.strptime(
            element['timestamp'], '%Y-%m-%dT%H:%M:%S%z'))
        temps.append(element['temperature'])
        precs.append(element['precipitation'])
        suns.append(element['sunshine'] / 0.6)
    dates = date2num(dates)

    current = []
    with urllib.request.urlopen(f"https://api.brightsky.dev/current_weather?lat={lat}&lon={lon}") as url:
        current = json.loads(url.read().decode())

    plot_count = 3
    fig, axs = plt.subplots(plot_count, 1, figsize=(14, 5 * plot_count))

    axs[0].scatter(dates, temps, c=temps)
    axs[0].title.set_text('Temperature (°C)')

    axs[1].bar(dates, precs)
    axs[1].title.set_text('Precipitation (mm/hour)')

    axs[2].bar(dates, suns, color='#D9822B')
    axs[2].title.set_text('Sunshine (percent/hour)')
    axs[2].set_ylim([0, 100])

    for ax in axs:
        ax.xaxis_date()
        ax.grid(which='major',)
        ax.set_xlim([dates[0], dates[len(dates) - 1]])
        ax.xaxis.set_major_formatter(DateFormatter('%a %d.%m'))
        ax.xaxis.set_major_locator(DayLocator())

    temp_name = tempfile.gettempdir() + '/' + next(tempfile._get_candidate_names()) + '.png'
    plt.savefig(temp_name, bbox_inches='tight')
    return {
        'plot': temp_name,
        'current_temp': current['weather']['temperature'],
        'current_str': current['weather']['condition'],
        'weather_station': weather_station.title(),
        'weather_station_distance': int(weather_station_distance / 100) / 10,
    }


def start(update: Update, context: CallbackContext):
    context.bot.send_message(
        chat_id=update.effective_chat.id, text="Send me locations and I will answer with the weather.")


def sendForecast(chat_id: Union[int, str], bot: Bot, lat: float, lon: float, duration: float = 14, name: str = None):
    result = fetchWeather(lat, lon, duration)
    station_text = f"forecast for {name}." if (
        name != None) else f"forecast for {result['weather_station']} ({result['weather_station_distance']}km from location)."
    bot.send_photo(chat_id, photo=open(
        result['plot'], 'rb'), caption=f"{duration} day {station_text}\nCurrently it is {result['current_temp']}°C and {result['current_str']}.")


def getStuff(update: Update, context: CallbackContext) -> Tuple[Union[int, str], str]:
    message = None
    if update.edited_message:
        message = update.edited_message
    else:
        message = update.message
    return (update.effective_chat.id, message)


def getLocationName(lat: float, lon: float) -> str:
    with urllib.request.urlopen(f"https://api.brightsky.dev/sources?lat={lat}&lon={lon}") as url:
        source = json.loads(url.read().decode())['sources'][0]
        return (source['station_name'].title(), int(source['distance'] / 100) / 10)


def addLocation(chat_id: Union[int, str], bot: Bot, lat: float, lon: float):
    locations = []
    if redisDB.exists(chat_id):
        locations = json.loads(redisDB.get(chat_id))
    name, dist = getLocationName(lat, lon)
    locations.append({
        'name': name,
        'lat': lat,
        'lon': lon
    })
    redisDB.set(chat_id, json.dumps(locations))
    bot.send_message(
        chat_id, f"Station '{name}' ({dist}km from location) added.\nIt will be included in '/getall' and you can get it individually by '/get {name}'.")


def getAll(update: Update, context: CallbackContext):
    chat_id, message = getStuff(update, context)
    if not redisDB.exists(chat_id):
        context.bot.send_message(
            chat_id, text=f"You need to add a location with '/add'.")
        return
    locations = json.loads(redisDB.get(chat_id))
    if len(locations) == 0:
        context.bot.send_message(
            chat_id, text=f"You need to add a location with '/add'.")
        return

    for location in locations:
        sendForecast(chat_id, context.bot,
                     location['lat'], location['lon'], name=location['name'])


def get(update: Update, context: CallbackContext):
    chat_id, message = getStuff(update, context)
    if not redisDB.exists(chat_id):
        context.bot.send_message(
            chat_id, text=f"You need to add a location with '/add'.")
        return

    locations = json.loads(redisDB.get(chat_id))
    if len(locations) == 0:
        context.bot.send_message(
            chat_id, text=f"You need to add a location with '/add'.")
        return

    locationNames = list(map(lambda x: x['name'], locations))
    if len(context.args) == 0:
        keyboard = []
        i = 0
        while i < len(locationNames) - 1:
            keyboard.append([
                InlineKeyboardButton(
                    locationNames[i], callback_data=locationNames[i]),
                InlineKeyboardButton(
                    locationNames[i + 1], callback_data=locationNames[i + 1]),
            ])
            i += 2

        if len(locationNames) - i == 1:
            keyboard.append([
                InlineKeyboardButton(
                    locationNames[i], callback_data=locationNames[i])
            ])
        logging.log(msg=f"{keyboard}", level=logging.INFO)
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(
            'Choose a station:', reply_markup=reply_markup)
        return

    if context.args[0] not in locationNames:
        context.bot.send_message(
            chat_id, text=f"You have not added {context.args[0]}.\n You have added {', '.join(locationNames)}.")
        return
    location = next(filter(lambda x: x['name'] == context.args[0], locations))
    sendForecast(chat_id, context.bot,
                 location['lat'], location['lon'], name=location['name'])


def locationHandle(update: Update, context: CallbackContext):
    chat_id, message = getStuff(update, context)
    lat = message.location.latitude
    lon = message.location.longitude
    if chat_id in chatIdsAddingLocations:
        addLocation(chat_id, context.bot, lat, lon)
    else:
        sendForecast(chat_id, context.bot, lat, lon)


def add(update: Update, context: CallbackContext):
    chat_id, message = getStuff(update, context)
    if chat_id in chatIdsAddingLocations:
        return
    chatIdsAddingLocations.append(chat_id)
    context.bot.send_message(chat_id, text="Ok, now send a location.")


def inlineButtonCallback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    query.edit_message_text(text=query.data)
    chat_id = query.message.chat_id
    locations = json.loads(redisDB.get(chat_id))
    location = next(filter(lambda x: x['name'] == query.data, locations))
    sendForecast(chat_id, context.bot,
                 location['lat'], location['lon'], name=location['name'])

updater = Updater(token=os.environ.get('BOT_TOKEN'))
dispatcher = updater.dispatcher

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(CommandHandler('add', add))
updater.dispatcher.add_handler(CallbackQueryHandler(inlineButtonCallback))
dispatcher.add_handler(CommandHandler('getAll', getAll))
dispatcher.add_handler(CommandHandler('get', get))
dispatcher.add_handler(MessageHandler(Filters.location, locationHandle))


updater.start_polling()
