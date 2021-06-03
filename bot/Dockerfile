FROM python:3.9.4-buster

WORKDIR /usr/src/app

RUN apt-get update \
  && apt-get install -y --no-install-recommends pkg-config software-properties-common dirmngr \
  && apt-key adv --keyserver keyserver.ubuntu.com --recv-keys E298A3A825C0D65DFD57CBB651716619E084DAB9 \
  && add-apt-repository "deb https://cloud.r-project.org/bin/linux/ubuntu $(lsb_release -cs)-cran40/" \
  && apt-get install -y --no-install-recommends r-base\
  && rm -rf /var/lib/apt/lists/*

RUN R -e "install.packages('ggplot2',dependencies=TRUE, repos='https://cloud.r-project.org/')"
RUN R -e "install.packages('rjson',dependencies=TRUE, repos='https://cloud.r-project.org/')"
RUN R -e "install.packages('wesanderson',dependencies=TRUE, repos='https://cloud.r-project.org/')"
RUN R -e "install.packages('gridExtra',dependencies=TRUE, repos='https://cloud.r-project.org/')"

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [ "python", "./main.py" ]