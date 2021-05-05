from datetime import datetime
import io
import json
import time
from typing import List, Optional, Tuple, TypedDict, cast
from requests.models import Response

from requests_cache import CachedSession

from PIL import Image, ImageDraw, ImageFont

from weatherProvider import plotForecast
import staticmaps
import imageio



requestsSession = CachedSession()


def printTime(s: str, t1: float, t2: float):
    print(f"{s}: {(t2 - t1) * 1000}ms")


ZOOM = 8
SIZE = 512

class RadarElement(TypedDict):
    time: int
    path: str

class Radar(TypedDict):
    past: List[RadarElement]
    nowcast: List[RadarElement]

class Satellite(TypedDict):
    infrared: List[RadarElement]
class WeatherMapsResult(TypedDict):
    version: str
    generated: int
    host: str
    radar: Radar
    satellite: Satellite

def getRainViewerUrls(lat: float, lon: float) -> List[Tuple[str, datetime]]:
    response = cast(Response, requestsSession.get('https://api.rainviewer.com/public/weather-maps.json', expire_after=5*60))
    result: WeatherMapsResult = response.json()
    items = result['radar']['past'][-3:] + result['radar']['nowcast']

    color = 2
    options = '1_1'
    return list(map(lambda item: (f"{result['host']}{item['path']}/{SIZE}/{ZOOM}/{lat}/{lon}/{color}/{options}.png", datetime.fromtimestamp(item['time'])), items))

def addTimeToImage(mapImage: Image.Image, timestamp: datetime):

    font = ImageFont.truetype('./bot/FiraSans-Regular.ttf', 15)
    text = timestamp.strftime('%Y-%m-%d %H:%M')
    dx, dy = font.getsize(text)
    timeImage = Image.new('RGBA', (dx + 20, dy + 20), (255, 255, 255, 128))
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(timeImage)  # type: ignore
    draw.text((10, 10), text, fill='black', font=font)
    mapImage.paste(timeImage, (0, 0), timeImage)


def addMarkerToImage(mapImage: Image.Image):
    marker = Image.open('./bot/marker2.png').resize((23, 34))
    x = int(mapImage.width / 2 - marker.width / 2)
    y = int(mapImage.height / 2 - marker.height)
    mapImage.paste(marker, (x, y), marker)


def createRadarAnimation(lat: float, lon: float):
    context = staticmaps.Context()
    context.set_tile_provider(staticmaps.tile_provider_OSM)
    location = staticmaps.create_latlng(lat, lon)
    context.set_center(location)
    context.set_zoom(ZOOM)
    mapImage = cast(Image.Image, context.render_pillow(SIZE, SIZE))

    allImages: List[Image.Image] = []

    radars = getRainViewerUrls(lat, lon)
    i = 0
    for radarUrl, timestamp in radars:
        t1 = time.perf_counter()
        currentImage = mapImage.copy()
        response = requestsSession.get(radarUrl)
        with Image.open(io.BytesIO(response.content)) as overlay:
            currentImage.paste(overlay, (0, 0), overlay)
        addTimeToImage(currentImage, timestamp)
        addMarkerToImage(currentImage)
        t2 = time.perf_counter()
        printTime(f'{i}', t1, t2)
        i += 1

        allImages.append(currentImage.convert('RGB'))
    mapImage.close()

    imageio.mimsave('map.mp4', allImages, fps=1)

def debugTest():
    pass
    forecast = {}
    with open('exampleWeather.json') as f:
        forecast = json.load(f)

    t1 = time.perf_counter()
    x = plotForecast(forecast, 'x')
    t2 = time.perf_counter()
    print(f"total: {(t2 - t1) * 1000}ms")
    with open('ggplot.jpg', 'wb') as f:
        f.write(x.getvalue())


if __name__ == "__main__":
    t1 = time.perf_counter()
    createRadarAnimation(51.8, 10.9)
    t2 = time.perf_counter()
    printTime('1 total:', t1, t2)
    # t1 = time.perf_counter()
    # createRadarAnimation(52.0, 13.0)
    # t2 = time.perf_counter()
    # printTime('2 total:', t1, t2)
