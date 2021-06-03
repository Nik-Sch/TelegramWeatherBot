import time
def printTime(s: str, t1: float, t2: float):
    print(f"{s}: {(t2 - t1) * 1000}ms")
    pass
t1 = time.perf_counter()

import rpy2.robjects as robjects
r = robjects.r
r['source']('plot.r')
plotFun = robjects.globalenv['plot']

t2 = time.perf_counter()
printTime('setup', t1, t2)

t1 = time.perf_counter()

plotFun('data.json', 'image.jpg', False)

t2 = time.perf_counter()
printTime('plot', t1, t2)
