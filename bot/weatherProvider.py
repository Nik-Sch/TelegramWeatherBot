
from datetime import datetime, timedelta
import json
import logging
import os
import matplotlib
import urllib.request
from typing import Any, List, Optional, Tuple, TypedDict
from numpy.lib import math
from scipy.signal import find_peaks
import numpy as np
import io
import time
from typing import Any, List
from mizani.formatters import date_format
import pandas as pd
from plotnine import ggplot
from plotnine.geoms.geom_bar import geom_bar
from plotnine.geoms.geom_point import geom_point
from plotnine.geoms.geom_text import geom_text
from plotnine.guides.guide_colorbar import guide_colorbar
from plotnine.guides.guides import guides
from plotnine.labels import ggtitle
from plotnine.mapping.aes import aes
from plotnine.scales.limits import ylim
from plotnine.scales.scale_color import scale_fill_gradient
from plotnine.scales.scale_xy import scale_x_datetime
from plotnine.themes.elements import element_blank
from plotnine.themes.theme import theme
from plotnine.themes.theme_minimal import theme_minimal
from scipy.signal import find_peaks
import numpy as np
from PIL import Image

matplotlib.use('cairo')

BRIGHTSKY_SERVER = "http://brightsky_frontend:5000"


class WeatherResult(TypedDict):
    plot: io.BytesIO
    duration: float
    current_temp: float
    current_str: str
    weather_station: str
    weather_station_distance: float


def concatImages(paths: List[str]) -> io.BytesIO:
    height = 0
    width = 10000000
    images = list(map(lambda p: Image.open(p), paths))
    for image in images:
        height += image.height
        width = min(width, image.width)
    combined = Image.new('RGB', (width, height))
    currentHeight = 0
    for image in images:
        combined.paste(image, (0, currentHeight))
        currentHeight += image.height
        image.close()
    for path in paths:
        os.remove(path)
    out = io.BytesIO()
    combined.save(out, format='jpeg')
    return out


def plotForecast(forecast: Any, id: str, hourlySun: bool = True) -> io.BytesIO:
    t1 = time.perf_counter()
    rainfallProb = {
        'dates': [],
        'amount': [],
        'percentage': [],
    }
    temps = {
        'dates': [],
        'temps': []
    }
    sunshine = {
        'dates': [],
        'sunshine': [],
        'label': []
    }
    for element in forecast['weather']:
        dateWithTime = datetime.strptime(element['timestamp'], '%Y-%m-%dT%H:%M:%S%z')
        date = dateWithTime.replace(hour=0, minute=0, second=0)
        if 'temperature' in element and element['temperature'] != None:
            temps['dates'].append(dateWithTime)
            temps['temps'].append(element['temperature'])
        if 'pp00' in element and element['pp00'] != None:
            rainfallProb['dates'].extend([dateWithTime] * 9)
            rainfallProb['amount'].append(5)
            rainfallProb['amount'].append(3)
            rainfallProb['amount'].append(2)
            rainfallProb['amount'].append(1)
            rainfallProb['amount'].append(0.5)
            rainfallProb['amount'].append(0.3)
            rainfallProb['amount'].append(0.2)
            rainfallProb['amount'].append(0.1)
            rainfallProb['amount'].append(0.0)
            rainfallProb['percentage'].append(element['pp50'])
            rainfallProb['percentage'].append(max(element['pp30'] - element['pp50'], 0))
            rainfallProb['percentage'].append(max(element['pp20'] - element['pp30'], 0))
            rainfallProb['percentage'].append(max(element['pp10'] - element['pp20'], 0))
            rainfallProb['percentage'].append(max(element['pp05'] - element['pp10'], 0))
            rainfallProb['percentage'].append(max(element['pp03'] - element['pp05'], 0))
            rainfallProb['percentage'].append(max(element['pp02'] - element['pp03'], 0))
            rainfallProb['percentage'].append(max(element['pp01'] - element['pp02'], 0))
            rainfallProb['percentage'].append(max(element['pp00'] - element['pp01'], 0))
        if 'sunshine' in element and element['sunshine'] != None:
            if hourlySun:
                try:
                    i = sunshine['dates'].index(date)
                    sunshine['sunshine'][i] += element['sunshine'] / 60.0
                except ValueError:
                    sunshine['dates'].append(date)
                    sunshine['sunshine'].append(element['sunshine'] / 60.0)
            else:
                sunshine['dates'].append(dateWithTime)
                sunshine['sunshine'].append(element['sunshine'])
    for i in range(len(sunshine['dates'])):
        sunshine['label'].append(f"{int(np.round(sunshine['sunshine'][i]))}{'h' if hourlySun else 'min'}")
    t2 = time.perf_counter()
    print(f"data: {(t2 - t1) * 1000}ms")

    customTheme = (
        theme_minimal()
        + theme(
            axis_title_x=element_blank(),
            axis_title_y=element_blank(),
            legend_position=(0.8, 0.8),
            legend_direction='horizontal',
            figure_size=(14, 5),
        )
    )
    xScale = scale_x_datetime(date_breaks='1 day', labels=date_format('%a %d.%m.'))

    images: List[str] = []

    t1 = time.perf_counter()
    if len(temps['dates']) > 0:
        maxima, _ = find_peaks(temps['temps'], prominence=1)
        maxima = list(maxima)
        tempMaxima = {
            'dates': np.array(temps['dates'])[maxima],
            'temps': np.array(temps['temps'])[maxima],
            'label': list(map(lambda x: f'{int(np.round(x))}°C', np.array(temps['temps'])[maxima])),
        }
        minima, _ = find_peaks(-np.array(temps['temps']), prominence=1)
        minima = list(minima)
        tempMinima = {
            'dates': np.array(temps['dates'])[minima],
            'temps': np.array(temps['temps'])[minima],
            'label': list(map(lambda x: f'{int(np.round(x))}°C', np.array(temps['temps'])[minima])),
        }

        tempPlot = (
            ggplot(pd.DataFrame(temps))
            + geom_point(aes(x='dates', y='temps', color='temps'))
            + geom_point(aes(x='dates', y='temps'), pd.DataFrame(tempMaxima), color='#C23030')
            + geom_text(aes(x='dates', y='temps', label='label'), pd.DataFrame(tempMaxima), color='#C23030', nudge_x=0.2, nudge_y=0.5)
            + geom_point(aes(x='dates', y='temps'), pd.DataFrame(tempMinima), color='#106BA3')
            + geom_text(aes(x='dates', y='temps', label='label'), pd.DataFrame(tempMinima), color='#106BA3', nudge_x=0.2, nudge_y=-0.5)
            + ggtitle('Temperature (°C)')
            + xScale
            + guides(color=False)
            + customTheme
        )
        filename = f'{id}-temp.jpg'
        tempPlot.save(filename)
        images.append(filename)

    t2 = time.perf_counter()
    print(f"temp: {(t2 - t1) * 1000}ms")

    t1 = time.perf_counter()
    if len(rainfallProb['dates']) > 0:
        rainplot = (
            ggplot(pd.DataFrame(rainfallProb))
            + geom_bar(aes(x='dates', y='percentage', fill='amount'), position='stack', stat='identity', width=1/24.0)
            + xScale
            + scale_fill_gradient('#84bcdb', '#084285')
            + ylim(0, 100)
            + ggtitle('Rain probability (%)')
            + guides(fill=guide_colorbar(title='mm', ticks=False))
            + customTheme
        )
        filename = f'{id}-rain.jpg'
        rainplot.save(filename)
        images.append(filename)

    t2 = time.perf_counter()
    print(f"rain: {(t2 - t1) * 1000}ms")

    t1 = time.perf_counter()
    if len(sunshine['dates']) > 0:
        sunPlot = (
            ggplot(pd.DataFrame(sunshine))
            + geom_bar(aes(x='dates', y='sunshine'), stat='identity', fill='#D9822B')
            + geom_text(aes(x='dates', y='sunshine', label='label'), color='#D9822B', nudge_y=0.5)
            + ggtitle(f"Sunshine ({'hours' if hourlySun else 'minutes'})")
            + xScale
            + guides(color=False)
            + customTheme
        )
        filename = f'{id}-sun.jpg'
        sunPlot.save(filename)
        images.append(filename)
    t2 = time.perf_counter()
    print(f"sun: {(t2 - t1) * 1000}ms")

    t1 = time.perf_counter()
    result = concatImages(images)
    t2 = time.perf_counter()
    print(f"concat: {(t2 - t1) * 1000}ms")
    return result



def fetchAndPlot(lat: float, lon: float, duration: float) -> Optional[WeatherResult]:
    if (duration > 10):
        duration = 10
    today = datetime.now().isoformat()
    lastday = (datetime.now() + timedelta(days=duration)).isoformat()
    forecast = {}
    try:
        with urllib.request.urlopen(f"{BRIGHTSKY_SERVER}/weather?lat={lat}&lon={lon}&date={today}&last_date={lastday}") as url:
            text = url.read().decode()
            forecast = json.loads(text)
    except Exception as e:
        logging.error(f"Couldn't fetch {lat}, {lon}, {e}")
        return None

    weather_station = forecast['sources'][0]['station_name']
    weather_station_distance = forecast['sources'][0]['distance']

    outbuffer = plotForecast(forecast, f"{lat}_{lon}", duration > 2)
    try:
        current = []
        with urllib.request.urlopen(f"{BRIGHTSKY_SERVER}/current_weather?lat={lat}&lon={lon}") as url:
            current = json.loads(url.read().decode())
        return {
            'plot': outbuffer,
            'duration': duration,
            'current_temp': current['weather']['temperature'],
            'current_str': current['weather']['condition'],
            'weather_station': weather_station.title(),
            'weather_station_distance': int(weather_station_distance / 100) / 10,
        }
    except:
        return {
            'plot': outbuffer,
            'duration': duration,
            'current_temp': math.nan,
            'current_str': 'Unknown',
            'weather_station': weather_station.title(),
            'weather_station_distance': int(weather_station_distance / 100) / 10,
        }


def getLocationInfo(lat: float, lon: float) -> Tuple[str, float]:
    with urllib.request.urlopen(f"{BRIGHTSKY_SERVER}/sources?lat={lat}&lon={lon}") as url:
        source = json.loads(url.read().decode())['sources'][0]
        return (source['station_name'].title(), int(source['distance'] / 100) / 10)
