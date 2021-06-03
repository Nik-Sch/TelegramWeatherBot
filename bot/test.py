import rpy2.robjects as robjects
r = robjects.r
r['source']('plot.r')
plotFun = robjects.globalenv['plot']

plotFun('data.json', 'image.jpg')
