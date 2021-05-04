FROM python:3.9.4-buster

WORKDIR /usr/src/app

RUN apt-get update \
  && apt-get install -y --no-install-recommends libcairo2-dev pkg-config \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [ "python", "./main.py" ]