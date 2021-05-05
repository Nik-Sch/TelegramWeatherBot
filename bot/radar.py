from datetime import datetime
import io
import time
from typing import List, Tuple, TypedDict, cast
from requests.models import Response
from PIL import Image, ImageDraw, ImageFont
import tempfile
import os
import staticmaps
import imageio
from timezonefinder import TimezoneFinder
import pytz
from db import requestsSession

timezoneFinder = TimezoneFinder()


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

    def resultFromElement(item: RadarElement): 
        tz = timezoneFinder.timezone_at(lat=float(lat), lng=float(lon))
        date = datetime.fromtimestamp(item['time'], tz=pytz.timezone(tz))
        url = f"{result['host']}{item['path']}/{SIZE}/{ZOOM}/{lat}/{lon}/{color}/{options}.png"
        return (url, date)

    return list(map(resultFromElement , items))

def addTimeToImage(mapImage: Image.Image, timestamp: datetime):

    font = ImageFont.truetype('./FiraSans-Regular.ttf', 15)
    text = timestamp.strftime('%Y-%m-%d %H:%M')
    dx, dy = font.getsize(text)
    timeImage = Image.new('RGBA', (dx + 20, dy + 20), (255, 255, 255, 128))
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(timeImage)  # type: ignore
    draw.text((10, 10), text, fill='black', font=font)
    mapImage.paste(timeImage, (0, 0), timeImage)


def addMarkerToImage(mapImage: Image.Image):
    marker = Image.open('./marker.png').resize((23, 34))
    x = int(mapImage.width / 2 - marker.width / 2)
    y = int(mapImage.height / 2 - marker.height)
    mapImage.paste(marker, (x, y), marker)


def createRadarAnimation(lat: float, lon: float) -> io.BytesIO:
    context = staticmaps.Context()
    context.set_tile_provider(staticmaps.tile_provider_OSM)
    location = staticmaps.create_latlng(float(lat), float(lon))
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

    f = tempfile.NamedTemporaryFile(suffix='.mp4').name
    imageio.mimsave(f, allImages, 'mp4',  fps=1)
    with open(f, 'rb') as fh:
        buffer = io.BytesIO(fh.read())
        os.remove(f)
        return buffer


if __name__ == "__main__":
    t1 = time.perf_counter()
    createRadarAnimation(51.8, 10.9)
    t2 = time.perf_counter()
    printTime('1 total:', t1, t2)
