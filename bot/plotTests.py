import json
import time
from typing import Any
from matplotlib import pyplot as plt
import plotly.express as px
import pandas as pd

from weatherProvider import plotTenDays

def plotPlotly(forecast: Any):
    rainfallProb = {
        'dates': [],
        '5mm': [],
        '3mm': [],
        '2mm': [],
        '1mm': [],
        '0.5mm': [],
        '0.3mm': [],
        '0.2mm': [],
        '0.1mm': [],
        '0.0mm': [],
    }
    for element in forecast['weather']:
        date = element['timestamp']
        if 'pp00' in element and element['pp00'] != None:
            rainfallProb['dates'].append(date)
            total = 0
            rainfallProb['5mm'].append(element['pp50'])
            rainfallProb['3mm'].append(max(element['pp30'] - element['pp50'], 0))
            rainfallProb['2mm'].append(max(element['pp20'] - element['pp30'], 0))
            rainfallProb['1mm'].append(max(element['pp10'] - element['pp20'], 0))
            rainfallProb['0.5mm'].append(max(element['pp05'] - element['pp10'], 0))
            rainfallProb['0.3mm'].append(max(element['pp03'] - element['pp05'], 0))
            rainfallProb['0.2mm'].append(max(element['pp02'] - element['pp03'], 0))
            rainfallProb['0.1mm'].append(max(element['pp01'] - element['pp02'], 0))
            rainfallProb['0.0mm'].append(max(element['pp00'] - element['pp01'], 0))
    data = pd.DataFrame(rainfallProb)
    fig = px.bar(data,
                 x='dates',
                 y=['5mm', '3mm', '2mm', '1mm', '0.5mm', '0.3mm', '0.2mm', '0.1mm', '0.0mm'],
                 color_discrete_sequence=[
                     '#08306b',
                     '#084285',
                     '#0a549e',
                     '#1966ad',
                     '#2979b9',
                     '#3b8bc2',
                     '#519ccc',
                     '#68acd5',
                     '#84bcdb',
                     '#a0cbe2',
                 ]
                 )
    fig.write_image('plotly.jpg')


def debugPlotly(forecast):
    plotPlotly(forecast)
    t1 = time.perf_counter()
    plotPlotly(forecast)
    t2 = time.perf_counter()
    print(f"plot: {(t2 - t1) * 1000}ms")


def debugMatplot(forecast):
    t1 = time.perf_counter()
    plotTenDays(forecast)
    t2 = time.perf_counter()
    print(f"plot: {(t2 - t1) * 1000}ms")
    t1 = time.perf_counter()
    plt.savefig('matplot.jpg', format='jpg', bbox_inches='tight')
    t2 = time.perf_counter()
    print(f"save: {(t2 - t1) * 1000}ms")


def debugTest():
    pass
    forecast = {}
    t1 = time.perf_counter()
    with open('exampleWeather.json') as f:
        forecast = json.load(f)
    t2 = time.perf_counter()
    print(f"json: {(t2 - t1) * 1000}ms")

    print('plotly:')
    debugPlotly(forecast)

    print('matplotlib:')
    debugMatplot(forecast)


if __name__ == "__main__":
    debugTest()
