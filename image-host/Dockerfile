FROM python:3.9.4-buster

WORKDIR /usr/src/app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [ "gunicorn", "--worker-class=gevent", "--graceful-timeout", "10", "-t", "9999", "-b", "0.0.0.0:80", "--worker-tmp-dir", "/dev/shm", "--access-logfile", "-", "--reload",  "main:app" ]