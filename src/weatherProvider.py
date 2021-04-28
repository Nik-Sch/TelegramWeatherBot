
from datetime import datetime, timedelta
import json
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.dates import (date2num,
                              DateFormatter,
                              DayLocator,
                              )
import urllib.request
import tempfile
from typing import List, Tuple, TypedDict, cast
from scipy.signal import find_peaks
import numpy as np

class WeatherResult(TypedDict):
    plot: str
    duration: float
    current_temp: float
    current_str: str
    weather_station: str
    weather_station_distance: float

def fetchAndPlot(lat: float, lon: float, duration: float, debug: bool = False) -> WeatherResult:
    if (duration > 10):
        duration = 10
    today = datetime.now().isoformat()
    lastday = (datetime.now() + timedelta(days=duration)).isoformat()
    forecast = {}
    with urllib.request.urlopen(f"https://api.brightsky.dev/weather?lat={lat}&lon={lon}&date={today}&last_date={lastday}") as url:
        forecast = json.loads(url.read().decode())
    weather_station = forecast['sources'][0]['station_name']
    weather_station_distance = forecast['sources'][0]['distance']
    datesD = []
    temps = []
    precs = []
    suns = []
    for element in forecast['weather']:
        datesD.append(datetime.strptime(
            element['timestamp'], '%Y-%m-%dT%H:%M:%S%z'))
        temps.append(element['temperature'])
        precs.append(element['precipitation'])
        suns.append(element['sunshine'])
    dates = np.array(date2num(datesD))
    temps = np.array(temps)
    precs = np.array(precs)
    suns = np.array(suns)

    plot_count = 3
    fig, axs = plt.subplots(plot_count, 1, figsize=(14, 5 * plot_count))
    axs = cast(List[Axes], axs)

    axs[0].scatter(dates, temps, c=temps)
    axs[0].title.set_text('Temperature (°C)')

    maxima, _ = find_peaks(temps, prominence=1)
    maxima = list(maxima)
    maxima.sort(key=lambda peak: temps[peak])
    maxima = maxima[-3:]
    axs[0].plot(dates[maxima], temps[maxima], 'x', c='#C23030')
    for peak in maxima:
        axs[0].text(dates[peak] + 0.1, temps[peak] + 0.1,
                    f"{int(np.round(temps[peak]))}°C", in_layout=True, c='#C23030')

    minima, _ = find_peaks(-temps, prominence=1)
    minima = list(minima)
    minima.sort(key=lambda peak: temps[peak])
    minima = minima[:3]
    axs[0].plot(dates[minima], temps[minima], 'x', c='#106BA3')
    for peak in minima:
        axs[0].text(dates[peak] + 0.1, temps[peak] - 0.1,
                    f"{int(np.round(temps[peak]))}°C", in_layout=True, va='top', c='#106BA3')
    axs[0].set_ylim([temps[minima[0]] - 1.2, temps[maxima[-1]] + 1.2])

    axs[1].bar(dates, precs, color='#106BA3')
    axs[1].title.set_text('Precipitation (mm/hour)')

    axs[2].bar(dates, suns, color='#D9822B')
    axs[2].title.set_text('Sunshine (minutes/hour)')
    axs[2].plot(dates, [60 for _ in range(len(dates))], color='black')
    axs[2].set_ylim([0, 65])

    for ax in axs:
        ax.xaxis_date()
        ax.grid(which='major',)
        ax.set_xlim([dates[0], dates[len(dates) - 1]])
        ax.xaxis.set_major_formatter(DateFormatter('%a %d.%m'))
        ax.xaxis.set_major_locator(DayLocator())
    temp_name = tempfile.gettempdir() + '/' + next(
        tempfile._get_candidate_names()  # type: ignore
    ) + '.png'
    if debug:
        plt.show()
    else:
        plt.savefig(temp_name, bbox_inches='tight')

    current = []
    with urllib.request.urlopen(f"https://api.brightsky.dev/current_weather?lat={lat}&lon={lon}") as url:
        current = json.loads(url.read().decode())
    return {
        'plot': temp_name,
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
    fetchAndPlot(52.180687, 13.579082, 14, debug=True)
