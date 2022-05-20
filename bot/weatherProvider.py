
from datetime import datetime, timedelta
import json
import logging
import tempfile
from typing import Any, Optional, Tuple, TypedDict
from numpy.lib import math
from requests_cache.session import CachedSession
import numpy as np
import io
import time
from typing import Any
import numpy as np
from backend import getRequestsCache
from radar import printTime
import rpy2.robjects as robjects

r = robjects.r
r['source']('plot.r')
rPlotFun = robjects.globalenv['plot']


# BRIGHTSKY_SERVER = "http://brightsky_frontend:5000"
BRIGHTSKY_SERVER = "https://api.brightsky.dev/"


class WeatherResult(TypedDict):
    plot: io.BytesIO
    duration: float
    current_temp: float
    current_str: str
    weather_station: str
    weather_station_distance: float


class WeatherProvider:

    requestsSession: CachedSession

    def __init__(self) -> None:
        self.requestsSession = getRequestsCache()

    def plotForecast(self, forecast: Any, id: str, hourlySun: bool = True) -> io.BytesIO:
        t1 = time.perf_counter()
        rainfallProb = {
            'dates': [],
            'amount': [],
            'percentage': [],
        }
        rainFallAmount = {
            'dates': [],
            'amount': []
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
        rainProps = {
            'pp50': 5,
            'pp30': 3,
            'pp20': 2,
            'pp10': 1,
            'pp05': 0.5,
            'pp03': 0.3,
            'pp02': 0.2,
            'pp01': 0.1,
            'pp00': 0,
        }
        for element in forecast['weather']:
            dateWithTime = datetime.strptime(element['timestamp'], '%Y-%m-%dT%H:%M:%S%z')
            datetimeStr = dateWithTime.strftime('%Y-%m-%dT%H:%M:%S%z')
            date = dateWithTime.replace(hour=0, minute=0, second=0)
            dateStr = date.strftime('%Y-%m-%dT%H:%M:%S%z')
            if 'temperature' in element and element['temperature'] != None:
                temps['dates'].append(datetimeStr)
                temps['temps'].append(element['temperature'])

            oldValue = 0
            for key, value in rainProps.items():
                if key in element and element[key] != None:
                    rainfallProb['dates'].append(datetimeStr)
                    rainfallProb['amount'].append(value)
                    rainfallProb['percentage'].append(max(element[key] - oldValue, 0))
                    oldValue = element[key]
            if 'precipitation' in element and element['precipitation'] != None:
                rainFallAmount['dates'].append(datetimeStr)
                rainFallAmount['amount'].append(element['precipitation'])

            if 'sunshine' in element and element['sunshine'] != None:
                if hourlySun:
                    try:
                        i = sunshine['dates'].index(dateStr)
                        sunshine['sunshine'][i] += element['sunshine'] / 60.0
                    except ValueError:
                        sunshine['dates'].append(dateStr)
                        sunshine['sunshine'].append(element['sunshine'] / 60.0)
                else:
                    sunshine['dates'].append(datetimeStr)
                    sunshine['sunshine'].append(element['sunshine'])
        for i in range(len(sunshine['dates'])):
            sunshine['label'].append(f"{int(np.round(sunshine['sunshine'][i]))}h")

        if len(rainfallProb['dates']) == 0:
            rainfallProb = None

        data = {
            'temps': temps,
            'rainfallProb': rainfallProb,
            'rainFallAmount': rainFallAmount,
            'sunshine': sunshine,
        }
        rInFile = tempfile.NamedTemporaryFile(suffix='.json').name
        rOutFile = tempfile.NamedTemporaryFile(suffix='.jpg').name
        with open(rInFile, 'w') as outfile:
            json.dump(data, outfile)
        t2 = time.perf_counter()
        printTime('data', t1, t2)

        t1 = time.perf_counter()
        rPlotFun(rInFile, rOutFile, hourlySun)
        t2 = time.perf_counter()
        printTime('plot', t1, t2)

        with open(rOutFile, 'rb') as infile:
            return io.BytesIO(infile.read())


    def fetchAndPlot(self, lat: float, lon: float, duration: float) -> Optional[WeatherResult]:
        if (duration > 10):
            duration = 10
        today = datetime.now().replace(minute=0, second=0, microsecond=0).isoformat()
        lastday = (datetime.now() + timedelta(days=duration)).replace(minute=0, second=0, microsecond=0).isoformat()
        forecast = {}
        try:
            forecast = self.requestsSession.get(f"{BRIGHTSKY_SERVER}/weather?lat={lat}&lon={lon}&date={today}&last_date={lastday}", expire_after=30*60).json()
        except Exception as e:
            logging.error(f"Couldn't fetch {lat}, {lon}, {e}")
            return None

        if 'sources' not in forecast or 'weather' not in forecast:
            logging.error(f"no sources or weather in forecast ({forecast})")
            return None

        weather_station = forecast['sources'][0]['station_name']
        weather_station_distance = forecast['sources'][0]['distance']

        outbuffer = self.plotForecast(forecast, f"{lat}_{lon}", duration > 2)
        try:
            current = self.requestsSession.get(f"{BRIGHTSKY_SERVER}/current_weather?lat={lat}&lon={lon}", expire_after=5*60).json()
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

    def getLocationInfo(self, lat: float, lon: float) -> Optional[Tuple[str, float]]:
        try:
            sources = self.requestsSession.get(f"{BRIGHTSKY_SERVER}/sources?lat={lat}&lon={lon}", expire_after=timedelta(days=7)).json()
            source = sources['sources'][0]
            return (source['station_name'].title(), int(source['distance'] / 100) / 10)
        except Exception:
            return None
