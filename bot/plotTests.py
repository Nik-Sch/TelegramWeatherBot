import json
import time

from weatherProvider import plotForecast


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
    debugTest()
