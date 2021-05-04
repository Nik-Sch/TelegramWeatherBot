
from datetime import datetime, timedelta
import json
import logging
from matplotlib import pyplot as plt
import matplotlib
import matplotlib.cm
from matplotlib.axes import Axes
from matplotlib.dates import (date2num,
                              DateFormatter,
                              DayLocator,
                              HourLocator,
                              )
import urllib.request
from typing import Any, Dict, List, Optional, Tuple, TypedDict, cast
from numpy.lib import math
from scipy.signal import find_peaks
import numpy as np
import io
import time

matplotlib.use('cairo')

BRIGHTSKY_SERVER = "http://brightsky_frontend:5000"


class WeatherResult(TypedDict):
    plot: io.BytesIO
    duration: float
    current_temp: float
    current_str: str
    weather_station: str
    weather_station_distance: float

probMM = [5.0, 3.0, 2.0, 1.0, 0.7, 0.5, 0.3, 0.2, 0.1, 0.0]

def plotTenDays(forecast: Any):
    temps: Dict[datetime, float] = {}
    rainfallProb: Dict[datetime, List[int]] = {}
    sunhours: Dict[datetime, float] = {}
    for element in forecast['weather']:
        dateWithTime = datetime.strptime(element['timestamp'], '%Y-%m-%dT%H:%M:%S%z')
        date = dateWithTime.replace(hour=0, minute=0, second=0)
        if 'temperature' in element and element['temperature'] != None:
            temps[dateWithTime] = element['temperature']
        if 'pp00' in element and element['pp00'] != None:
            rainfallProb[dateWithTime] = [
                element['pp50'],
                element['pp30'],
                element['pp20'],
                element['pp10'],
                element['pp07'],
                element['pp05'],
                element['pp03'],
                element['pp02'],
                element['pp01'],
                element['pp00'],
                ]
        if 'sunshine' in element and element['sunshine'] != None:
            sunhours[date] = sunhours.get(date, 0) + element['sunshine']

    plot_count = (len(temps) > 0) + (len(rainfallProb) > 0) + (len(sunhours) > 0)
    fig, axs = plt.subplots(plot_count, 1, figsize=(14, 5 * plot_count))
    axs = cast(List[Axes], axs)

    current = 0

    if len(temps) > 0:
        x, y = zip(*sorted(temps.items()))
        tempDates = np.array(date2num(x))
        tempValues = np.array(y)

        axs[current].scatter(tempDates, tempValues, c=tempValues)
        axs[current].title.set_text('Temperature (°C)')

        maxima, _ = find_peaks(tempValues, prominence=1)
        maxima = list(maxima)
        maxima.sort(key=lambda peak: tempValues[peak])
        axs[current].plot(tempDates[maxima], tempValues[maxima], 'x', c='#C23030')
        for peak in maxima:
            axs[current].text(tempDates[peak] + 0.1, tempValues[peak] + 0.1,
                        f"{int(np.round(tempValues[peak]))}°C", in_layout=True, c='#C23030')

        minima, _ = find_peaks(-tempValues, prominence=1)
        minima = list(minima)
        minima.sort(key=lambda peak: tempValues[peak])
        axs[current].plot(tempDates[minima], tempValues[minima], 'x', c='#106BA3')
        for peak in minima:
            axs[current].text(tempDates[peak] + 0.1, tempValues[peak] - 0.1,
                        f"{int(np.round(tempValues[peak]))}°C", in_layout=True, va='top', c='#106BA3')

        axs[current].set_ylim([min(tempValues) - 1.2,
                        max(tempValues) + 1.2])
        axs[current].set_xlim(tempDates[0], tempDates[-1])
        axs[current].grid(which='major',)
        current += 1

    if len(rainfallProb) > 0:
        x, y = zip(*sorted(rainfallProb.items()))
        probDates = np.array(date2num(x))
        probValues = np.array(y)
        nextBottom = np.zeros((len(rainfallProb),), dtype=np.int32)
        cmap = matplotlib.cm.get_cmap('Blues')
        for i in range(len(probMM)):
            currentValues = np.array([x[i] for x in probValues])
            axs[current].bar(probDates, currentValues - nextBottom, bottom=nextBottom, label=f"{probMM[i]}mm", width=1/24.0, color=cmap(0.3 + 0.7 * (1 - i/len(probMM))))
            nextBottom += currentValues - nextBottom
        axs[current].title.set_text('Precipitation Probability in percent')
        axs[current].set_xlim(probDates[0], probDates[-1])
        axs[current].set_ylim(0, 100)
        handles, labels = axs[current].get_legend_handles_labels()
        axs[current].legend(reversed([handles[0], handles[int(len(probMM) / 2)], handles[len(probMM) - 1]]),
                            reversed([labels[0],  labels[int(len(probMM) / 2)],  labels[len(probMM) - 1]]))

        current += 1

    if len(sunhours) > 0:
        x, y = zip(*sorted(sunhours.items()))
        sunDates = np.array(date2num(x))
        sunValues = np.array(y) / 60
        axs[current].bar(sunDates, sunValues, color='#D9822B')
        axs[current].title.set_text('Sunshine (hours/day)')
        axs[current].set_xlim(sunDates[0] - 0.5, sunDates[-1] + 0.5)
        axs[current].set_ylim([0, max([8, max(sunValues) + 0.5])])
        axs[current].grid(axis='y')
        for i in range(len(sunValues)):
            if sunValues[i] > 0:
                axs[current].text(sunDates[i], sunValues[i] + 0.2,
                                  f"{int(np.round(sunValues[i]))}h", in_layout=True, ha='center', c='#D9822B')
        current += 1

    for ax in axs[:current]:
        ax.xaxis_date()
        ax.xaxis.set_major_formatter(DateFormatter('%a %d.%m.'))
        ax.xaxis.set_major_locator(DayLocator())


def plotShort(forecast: Any):
    temps: Dict[datetime, float] = {}
    sunhours: Dict[datetime, float] = {}
    rainfallProb: Dict[datetime, List[int]] = {}
    for element in forecast['weather']:
        dateWithTime = datetime.strptime(element['timestamp'], '%Y-%m-%dT%H:%M:%S%z')
        if 'temperature' in element and element['temperature'] != None:
            temps[dateWithTime] = element['temperature']
        if 'sunshine' in element and element['sunshine'] != None:
            sunhours[dateWithTime] = element['sunshine']
        if 'pp00' in element and element['pp00'] != None:
            rainfallProb[dateWithTime] = [
                element['pp50'],
                element['pp30'],
                element['pp20'],
                element['pp10'],
                element['pp07'],
                element['pp05'],
                element['pp03'],
                element['pp02'],
                element['pp01'],
                element['pp00'],
            ]

    plot_count = (len(temps) > 0) + (len(rainfallProb) > 0) + (len(sunhours) > 0)
    _, axs = plt.subplots(plot_count, 1, figsize=(14, 5 * plot_count))
    axs = cast(List[Axes], axs)

    current = 0

    if len(temps) > 0:
        x, y = zip(*sorted(temps.items()))
        tempDates = np.array(date2num(x))
        tempValues = np.array(y)

        axs[current].scatter(tempDates, tempValues, c=tempValues)
        axs[current].title.set_text('Temperature (°C)')
        axs[current].set_ylim([min(tempValues) - 1.2, max(tempValues) + 1.2])
        axs[current].set_xlim(tempDates[0], tempDates[-1])
        current += 1

    if len(rainfallProb) > 0:
        x, y = zip(*sorted(rainfallProb.items()))
        probDates = np.array(date2num(x))
        probValues = np.array(y)
        nextBottom = np.zeros((len(rainfallProb),), dtype=np.int32)
        cmap = matplotlib.cm.get_cmap('Blues')
        for i in range(len(probMM)):
            currentValues = np.array([x[i] for x in probValues])
            axs[current].bar(probDates, currentValues - nextBottom, bottom=nextBottom, label=f"{probMM[i]}mm", width=0.035, color=cmap(0.3 + 0.7 * (1 - i/len(probMM))))
            nextBottom += currentValues - nextBottom
        axs[current].title.set_text('Precipitation Probability')
        axs[current].set_xlim(probDates[0], probDates[-1])
        axs[current].set_ylim(0, 100)
        handles, labels = axs[current].get_legend_handles_labels()
        axs[current].legend(reversed([handles[0], handles[int(len(probMM) / 2)], handles[len(probMM) - 1]]),
                            reversed([labels[0],  labels[int(len(probMM) / 2)],  labels[len(probMM) - 1]]))

        current += 1

    if len(sunhours) > 0:
        x, y = zip(*sorted(sunhours.items()))
        sunDates = np.array(date2num(x))
        sunValues = np.array(y)
        axs[current].bar(sunDates, sunValues, color='#D9822B', width=0.035)
        axs[current].title.set_text('Sunshine (min/hour)')
        axs[current].set_xlim(sunDates[0], sunDates[-1])
        axs[current].set_ylim([0, 65])
        axs[current].plot(sunDates, np.full((len(sunDates)), 60), color='black')
        current += 1

    for ax in axs[:current]:
        ax.xaxis_date()
        ax.grid(which='major')
        ax.xaxis.set_major_formatter(DateFormatter('%a %H:00'))
        ax.xaxis.set_major_locator(HourLocator(interval=4))


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
        logging.log(msg=f"Couldn't fetch {lat}, {lon}, {e}", level=logging.ERROR)
        return None

    weather_station = forecast['sources'][0]['station_name']
    weather_station_distance = forecast['sources'][0]['distance']

    t1 = time.perf_counter()
    if duration > 2:
        plotTenDays(forecast)
    else:
        plotShort(forecast)
    t2 = time.perf_counter()
    logging.info(f'plotCall: {(t2 - t1) * 1000}ms')
    outbuffer = io.BytesIO()
    t1 = time.perf_counter()
    plt.savefig(outbuffer, format='jpeg', bbox_inches='tight')
    outbuffer.seek(0)
    t2 = time.perf_counter()
    logging.info(f'savefig: {(t2 - t1) * 1000}ms')
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