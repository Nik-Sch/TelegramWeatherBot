from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import os
import logging
import urllib.request
import json
from datetime import datetime, timedelta
from matplotlib import pyplot as plt
from matplotlib.dates import date2num, DateFormatter
import tempfile
# import numpy as np

def fetchWeather(lat, lon):
  today = datetime.now().isoformat()
  lastday = (datetime.now() + timedelta(days=14)).isoformat()
  with urllib.request.urlopen(f"https://api.brightsky.dev/weather?lat={lat}&lon={lon}&date={today}&last_date={lastday}") as url:
    data = json.loads(url.read().decode())
    dates = []
    temps = []
    precs = []
    suns = []
    for element in data['weather']:
      dates.append(datetime.strptime(
          element['timestamp'], '%Y-%m-%dT%H:%M:%S%z'))
      temps.append(element['temperature'])
      precs.append(element['precipitation'])
      suns.append(element['sunshine'] / 0.6)
    dates = date2num(dates)


    plot_count = 3
    fig, (ax1, ax2, ax3) = plt.subplots(plot_count, 1, figsize=(14, 5 * plot_count))
    ax1.scatter(dates, temps, c=temps)
    ax1.xaxis_date()
    ax1.title.set_text('Temperature (°C)')
    ax1.grid(which='major',)

    ax2.bar(dates, precs)
    ax2.xaxis_date()
    ax2.title.set_text('Precipitation (mm)')
    ax2.grid(which='major',)

    ax3.bar(dates, suns, color='#D9822B')
    ax3.xaxis_date()
    ax3.title.set_text('Sunshine (percent/hour)')
    ax3.grid(which='major',)

    ax1.xaxis.set_major_formatter(DateFormatter('%a %d.%m'))
    ax2.xaxis.set_major_formatter(DateFormatter('%a %d.%m'))
    ax3.xaxis.set_major_formatter(DateFormatter('%a %d.%m'))


    temp_name = tempfile.gettempdir() + '/' + next(tempfile._get_candidate_names()) + '.png'
    plt.savefig(temp_name, bbox_inches='tight')
    return temp_name


updater = Updater(token=os.environ.get('BOT_TOKEN'))
dispatcher = updater.dispatcher

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)


def start(update: Updater, context: CallbackContext):
    context.bot.send_message(
        chat_id=update.effective_chat.id, text="Send me locations and I will answer with the weather.")

def locationHandle(update: Updater, context: CallbackContext):
    message = None
    if update.edited_message:
        message = update.edited_message
    else:
        message = update.message
    chat_id = update.effective_chat.id

    fileName = fetchWeather(message.location.latitude, message.location.longitude)
    print(fileName)
    context.bot.send_message(
        chat_id=update.effective_chat.id, text=f"lat: {message.location.latitude}, lon: {message.location.longitude}.")
    context.bot.send_photo(chat_id, photo=open(fileName, 'rb'))

dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(MessageHandler(Filters.location, locationHandle))


updater.start_polling()
