
from datetime import datetime, timedelta
import json
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.dates import (date2num,
                              DateFormatter,
                              DayLocator,
                              HourLocator,
                              )
import urllib.request
import tempfile
from typing import Any, Dict, List, Tuple, TypedDict, cast
from scipy.signal import find_peaks
import numpy as np
import io


class WeatherResult(TypedDict):
    plot: io.BytesIO
    duration: float
    current_temp: float
    current_str: str
    weather_station: str
    weather_station_distance: float


def plotOverview(forecast: Any):
    temps: Dict[datetime, float] = {}
    rainfall: Dict[datetime, float] = {}
    sunhours: Dict[datetime, float] = {}
    for element in forecast['weather']:
        dateWithTime = datetime.strptime(element['timestamp'], '%Y-%m-%dT%H:%M:%S%z')
        date = dateWithTime.replace(hour=0, minute=0, second=0)
        temps[dateWithTime] = temps.get(dateWithTime, 0) + element['temperature']
        rainfall[date] = rainfall.get(date, 0) + element['precipitation']
        sunhours[date] = sunhours.get(date, 0) + element['sunshine']

    plot_count = 3
    fig, axs = plt.subplots(plot_count, 1, figsize=(14, 5 * plot_count))
    axs = cast(List[Axes], axs)

    x, y = zip(*sorted(temps.items()))
    tempDates = np.array(date2num(x))
    tempValues = np.array(y)

    axs[0].scatter(tempDates, tempValues, c=tempValues)
    axs[0].title.set_text('Temperature (°C)')

    maxima, _ = find_peaks(tempValues, prominence=1)
    maxima = list(maxima)
    maxima.sort(key=lambda peak: tempValues[peak])
    maxima = maxima[-3:]
    axs[0].plot(tempDates[maxima], tempValues[maxima], 'x', c='#C23030')
    for peak in maxima:
        axs[0].text(tempDates[peak] + 0.1, tempValues[peak] + 0.1,
                    f"{int(np.round(tempValues[peak]))}°C", in_layout=True, c='#C23030')

    minima, _ = find_peaks(-tempValues, prominence=1)
    minima = list(minima)
    minima.sort(key=lambda peak: tempValues[peak])
    minima = minima[:3]
    axs[0].plot(tempDates[minima], tempValues[minima], 'x', c='#106BA3')
    for peak in minima:
        axs[0].text(tempDates[peak] + 0.1, tempValues[peak] - 0.1,
                    f"{int(np.round(tempValues[peak]))}°C", in_layout=True, va='top', c='#106BA3')

    axs[0].set_ylim([min(tempValues) - 1.2,
                    max(tempValues) + 1.2])
    axs[0].set_xlim(tempDates[0], tempDates[-1])
    axs[0].grid(which='major',)

    x, y = zip(*sorted(rainfall.items()))
    rainDates = np.array(date2num(x))
    rainValues = np.array(y)
    axs[1].bar(rainDates, rainValues, color='#106BA3')
    axs[1].title.set_text('Precipitation (mm/day)')
    axs[1].set_xlim(rainDates[0] - 0.5, rainDates[-1] + 0.5)
    axs[1].set_ylim([0, max([8, max(rainValues) + 1])])
    axs[1].grid(axis='y')
    for i in range(len(rainValues)):
        if rainValues[i] > 0:
            axs[1].text(rainDates[i], rainValues[i] + 0.2,
                        f"{int(np.round(rainValues[i]))}mm", in_layout=True, ha='center', c='#106BA3')

    x, y = zip(*sorted(sunhours.items()))
    sunDates = np.array(date2num(x))
    sunValues = np.array(y) / 60
    axs[2].bar(sunDates, sunValues, color='#D9822B')
    axs[2].title.set_text('Sunshine (hours/day)')
    axs[2].set_xlim(sunDates[0] - 0.5, sunDates[-1] + 0.5)
    axs[2].set_ylim([0, max([8, max(sunValues) + 0.5])])
    axs[2].grid(axis='y')
    for i in range(len(sunValues)):
        if sunValues[i] > 0:
            axs[2].text(sunDates[i], sunValues[i] + 0.2,
                        f"{int(np.round(sunValues[i]))}h", in_layout=True, ha='center', c='#D9822B')

    for ax in axs[:3]:
        ax.xaxis_date()
        ax.xaxis.set_major_formatter(DateFormatter('%a %d.%m.'))
        ax.xaxis.set_major_locator(DayLocator())


def plotDetailed(forecast: Any):
    temps: Dict[datetime, float] = {}
    rainfall: Dict[datetime, float] = {}
    sunhours: Dict[datetime, float] = {}
    for element in forecast['weather']:
        dateWithTime = datetime.strptime(element['timestamp'], '%Y-%m-%dT%H:%M:%S%z')
        temps[dateWithTime] = temps.get(dateWithTime, 0) + element['temperature']
        rainfall[dateWithTime] = rainfall.get(dateWithTime, 0) + element['precipitation']
        sunhours[dateWithTime] = sunhours.get(dateWithTime, 0) + element['sunshine']

    plot_count = 3
    fig, axs = plt.subplots(plot_count, 1, figsize=(14, 5 * plot_count))
    axs = cast(List[Axes], axs)

    x, y = zip(*sorted(temps.items()))
    tempDates = np.array(date2num(x))
    tempValues = np.array(y)

    axs[0].scatter(tempDates, tempValues, c=tempValues)
    axs[0].title.set_text('Temperature (°C)')
    axs[0].set_ylim([min(tempValues) - 1.2, max(tempValues) + 1.2])
    axs[0].set_xlim(tempDates[0], tempDates[-1])

    x, y = zip(*sorted(rainfall.items()))
    rainDates = np.array(date2num(x))
    rainValues = np.array(y)
    axs[1].bar(rainDates, rainValues, color='#106BA3')
    axs[1].title.set_text('Precipitation (mm/hour)')
    axs[1].set_xlim(rainDates[0], rainDates[-1])
    axs[1].set_ylim([0, max([2, max(rainValues) + 1])])

    x, y = zip(*sorted(sunhours.items()))
    sunDates = np.array(date2num(x))
    sunValues = np.array(y)
    axs[2].bar(sunDates, sunValues, color='#D9822B')
    axs[2].title.set_text('Sunshine (min/hour)')
    axs[2].set_xlim(sunDates[0], sunDates[-1])
    axs[2].set_ylim([0, 65])
    axs[2].plot(sunDates, np.full((len(sunDates)), 60), color='black')

    for ax in axs[:3]:
        ax.xaxis_date()
        ax.grid(which='major')
        ax.xaxis.set_major_formatter(DateFormatter('%a %H:00'))
        ax.xaxis.set_major_locator(HourLocator(interval=4))


def fetchAndPlot(lat: float, lon: float, duration: float, debug: bool = False, jpeg: bool = False) -> WeatherResult:
    if (duration > 10):
        duration = 10
    today = datetime.now().isoformat()
    lastday = (datetime.now() + timedelta(days=duration)).isoformat()
    forecast = {}
    with urllib.request.urlopen(f"https://api.brightsky.dev/weather?lat={lat}&lon={lon}&date={today}&last_date={lastday}") as url:
        forecast = json.loads(url.read().decode())
    weather_station = forecast['sources'][0]['station_name']
    weather_station_distance = forecast['sources'][0]['distance']

    if duration > 2:
        plotOverview(forecast)
    else:
        plotDetailed(forecast)

    # temp_name = tempfile.gettempdir() + '/' + next(
    #     tempfile._get_candidate_names()  # type: ignore
    # ) + ('.jpeg' if jpeg else '.png')
    outbuffer = io.BytesIO()
    if debug:
        plt.show()
    else:
        plt.savefig(outbuffer, format='jpeg' if jpeg else 'png', bbox_inches='tight')
        outbuffer.seek(0)

    current = []
    with urllib.request.urlopen(f"https://api.brightsky.dev/current_weather?lat={lat}&lon={lon}") as url:
        current = json.loads(url.read().decode())
    return {
        'plot': outbuffer,
        'duration': duration,
        'current_temp': current['weather']['temperature'],
        'current_str': current['weather']['condition'],
        'weather_station': weather_station.title(),
        'weather_station_distance': int(weather_station_distance / 100) / 10,
    }


def getLocationInfo(lat: float, lon: float) -> Tuple[str, float]:
    with urllib.request.urlopen(f"https://api.brightsky.dev/sources?lat={lat}&lon={lon}") as url:
        source = json.loads(url.read().decode())['sources'][0]
        return (source['station_name'].title(), int(source['distance'] / 100) / 10)


if __name__ == "__main__":
    fetchAndPlot(52.180687, 13.579082, 1.5, debug=True)
