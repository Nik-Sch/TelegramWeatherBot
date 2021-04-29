FROM python:3.9.4-buster

WORKDIR /usr/src/app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [ "gunicorn", "main:app" ]