FROM python:3.9.4-buster

WORKDIR /usr/src/app
# RUN RUN apt-get update \
#   && apt-get install -y --no-install-recommends libsodium-dev mariadb-client \
#   && rm -rf /var/lib/apt/lists

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY src/ .

CMD [ "python", "./main.py" ]