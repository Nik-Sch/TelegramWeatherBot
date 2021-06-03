library(ggplot2)
library(rjson)
library(quantmod)
library(wesanderson)
library(gridExtra)

plot <- function(inputFile, outputFile) {
    forecast <- fromJSON(file = inputFile)

    customTheme <- (
                theme_minimal() +
                theme(
                    axis.title.x=element_blank(),
                    legend.position=c(0.8, 0.8),
                    legend.direction='horizontal',
                    plot.title = element_text(hjust = 0.5)
                    # figure.size=c(14, 5),
                )
            )

    xScale <- scale_x_datetime(
        date_breaks='5 hour',
        date_labels='%a %H:%M')

    asDate <- function(s) {
        return(as.POSIXct(sub("(.*?:.*?):(\\d\\d)", "\\1\\2", s), format="%Y-%m-%dT%H:%M:%S%z"))
    }

    if (!is.null(forecast$temps)) {
        tempsFrame <- as.data.frame(forecast$temps)
        peaks <- findPeaks(tempsFrame$temps, 0) - 1
        peakFrame <- data.frame(
            temps=tempsFrame$temps[peaks],
            dates=tempsFrame$dates[peaks],
            label=sprintf("%d°C", round(tempsFrame$temps[peaks]))
        )
        valleys <- findValleys(tempsFrame$temps, 0) - 1
        valleyFrame <- data.frame(
            temps=tempsFrame$temps[valleys],
            dates=tempsFrame$dates[valleys],
            label=sprintf("%d°C", round(tempsFrame$temps[valleys]))
        )
        palette = pal <- wes_palette("Zissou1", 100, type = "continuous")
        plotTemps <- ggplot(tempsFrame) +
        geom_point(aes(x=asDate(dates), y=temps, color=temps)) +
        geom_point(aes(x=asDate(dates), y=temps), peakFrame, color='#C23030') +
        geom_text(aes(x=asDate(dates), y=temps, label=label), peakFrame, color='#C23030', nudge_x=0.02, nudge_y=0.5) +
        geom_point(aes(x=asDate(dates), y=temps), valleyFrame, color='#106BA3') +
        geom_text(aes(x=asDate(dates), y=temps, label=label), valleyFrame, color='#106BA3', nudge_x=0.02, nudge_y=-0.5) +
        ylab('Temperature (°C)') +
        xScale +
        guides(color=FALSE) +
        scale_color_gradientn(colours = palette) +
        customTheme
    }

    if (!is.null(forecast$rainfallProb)) {

        rainfallProb <- as.data.frame(forecast$rainfallProb)
        rainfallAmount <- as.data.frame(forecast$rainFallAmount)
        amountLimit <- max(c(max(rainfallAmount$amount), 2))
        amountCoefficient <- amountLimit / 100

        plotRain <- ggplot() +
        geom_bar(aes(x=asDate(dates), y=percentage, fill=amount), rainfallProb, position='stack', stat='identity') +
        geom_line(aes(x=asDate(dates), y=amount / amountCoefficient), rainfallAmount, color='#8043cc') +
        scale_y_continuous(
            name='Rain probability (%)',
            limits=c(0, 100),
            sec.axis=sec_axis(~.*amountCoefficient, name='Rain in mm')
        ) +
        scale_fill_gradient(low='#84bcdb', high='#084285') +
        xScale +
        guides(fill=guide_colorbar(title='mm', ticks=FALSE)) +
        customTheme +
        theme(
            axis.title.y = element_text(color = '#84bcdb'),
            axis.title.y.right = element_text(color = '#8043cc')
        )
    }


    if (!is.null(forecast$sunshine)) {
        sunFrame <-as.data.frame(forecast$sunshine)

        plotSun <- ggplot(sunFrame) +
            geom_bar(aes(x=asDate(dates), y=sunshine), stat='identity', fill='#D9822B') +
            ylim(0, 60) +
            ylab('Sunshine (minutes)') +
            xScale +
            guides(color=FALSE) +
            customTheme
    }

    if (!is.null(plotTemps) && !is.null(plotRain) && !is.null(plotSun)) {
        g <- grid.arrange(plotTemps, plotRain, plotSun, ncol=1)
        ggsave(file=outputFile, g)
    } else {
        print('not all plots')
    }
}