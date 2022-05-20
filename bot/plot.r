library(ggplot2)
library(jsonlite)
library(wesanderson)
library(gridExtra)
library(lubridate)

findExtrema <- function(data, regex, offset) {
    xc <- paste(as.character(sign(diff(data))), collapse="")
    xc <- gsub("1", "+", gsub("-1", "-", xc))
    res <- gregexpr(regex, xc)[[1]] + offset
    attributes(res) <- NULL
    return(res)
}

findPeaks <- function(data) {
    return(findExtrema(data, "[+]{2}.{4}[-]{2}", 6))
}
findValleys <- function(data) {
    return(findExtrema(data, "[-]{2}.{4}[+]{2}", 6))
}

plot <- function(inputFile, outputFile, tenDays) {
    forecast <- fromJSON(inputFile)

    customTheme <- (
                theme_minimal() +
                theme(
                    axis.title.x=element_blank(),
                    legend.position=c(0.8, 0.8),
                    legend.direction='horizontal',
                    plot.title = element_text(hjust = 0.5),
                    panel.grid.minor = element_line(size = 0.5, color = "gray70")
                    # figure.size=c(14, 5),
                )
            )

    asDate <- function(s) {
        return(as.POSIXct(s, format="%Y-%m-%dT%H:%M:%S%z"))
    }

    asDateHour12 <- function(s) {
        res <- as.POSIXct(s, format="%Y-%m-%dT%H:%M:%S%z")
        hour(res) <- 11
        return(res)
    }

    minLimit <- asDate(min(forecast$temps$dates))
    hour(minLimit) <- 0
    maxLimit <- asDate(max(forecast$temps$dates))
    hour(minLimit) <- 23

    xScale <- scale_x_datetime(
        limits = if (tenDays) c(minLimit, maxLimit) else NULL,
        date_breaks=if (tenDays) '24 hour' else '4 hours',
        date_labels=if (tenDays) '%a %d.%m.' else '%a %H:%M')

    if (!is.null(forecast$temps)) {
        tempsFrame <- as.data.frame(forecast$temps)
        peaks <- findPeaks(tempsFrame$temps)
        peakFrame <- data.frame(
            temps=tempsFrame$temps[peaks],
            dates=tempsFrame$dates[peaks],
            label=sprintf("%d°C", round(tempsFrame$temps[peaks]))
        )
        valleys <- findValleys(tempsFrame$temps)
        valleyFrame <- data.frame(
            temps=tempsFrame$temps[valleys],
            dates=tempsFrame$dates[valleys],
            label=sprintf("%d°C", round(tempsFrame$temps[valleys]))
        )
        palette = pal <- wes_palette("Zissou1", 100, type = "continuous")
        xNudge <- if (tenDays) 5 * 3600 else 3600
        plotTemps <- ggplot(tempsFrame) +
        geom_point(aes(x=asDate(dates), y=temps, color=temps)) +
        geom_point(aes(x=asDate(dates), y=temps), peakFrame, color='#C23030') +
        geom_text(aes(x=asDate(dates), y=temps, label=label), peakFrame, color='#C23030', nudge_x=xNudge, nudge_y=1) +
        geom_point(aes(x=asDate(dates), y=temps), valleyFrame, color='#106BA3') +
        geom_text(aes(x=asDate(dates), y=temps, label=label), valleyFrame, color='#106BA3', nudge_x=xNudge, nudge_y=-1) +
        ylab('Temperature (°C)') +
        xScale +
        guides(color=FALSE) +
        scale_color_gradientn(colours = palette) +
        customTheme
    }


    rainfallAmount <- as.data.frame(forecast$rainFallAmount)
    amountLimit <- max(c(max(rainfallAmount$amount) + 1, 2))

    plotRain <- ggplot() +
    geom_bar(aes(x=asDate(dates), y=amount), rainfallAmount, stat='identity', fill='#2D72D2') +
    ylab('Rain in mm/hour') +
    ylim(0, amountLimit) +
    xScale +
    guides(color=FALSE) +
    customTheme


    if (!is.null(forecast$sunshine)) {
        sunFrame <-as.data.frame(forecast$sunshine)

        plotSun <- ggplot(sunFrame) +
            geom_bar(aes(x=if (tenDays) asDateHour12(dates) else asDate(dates), y=sunshine), stat='identity', fill='#D9822B') +
            ylab(if (tenDays) 'Sunshine (hours)' else 'Sunshine (minutes)') +
            xScale +
            guides(color=FALSE) +
            customTheme
        if (tenDays) {
            plotSun <- plotSun +
                geom_text(aes(x=if (tenDays) asDateHour12(dates) else asDate(dates), y=sunshine, label=label), color='#D9822B', nudge_y=1) +
                ylim(0, max(max(sunFrame$sunshine) + 1, 10))

        } else {
            plotSun <- plotSun +
                ylim(0, 60)
        }
    }

    if (!is.null(plotTemps) && !is.null(plotRain) && !is.null(plotSun)) {
        g <- grid.arrange(plotTemps, plotRain, plotSun, ncol=1)
        ggsave(file=outputFile, g, width=10, height=10)
    } else {
        print('not all plots')
    }
}

# plot('data.json', 'image.jpg', TRUE)
