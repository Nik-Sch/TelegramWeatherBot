from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
from typing import Any
from flask import Flask, request, jsonify
from flask.helpers import make_response, send_from_directory
from flask.wrappers import Response
import hashlib
from PIL import Image
import socket
import gevent

app = Flask(__name__)

@app.errorhandler(404)
def e404(_):
    return make_response(jsonify({'status': 404}), 404)


@app.errorhandler(405)
def e405(_):
    return make_response(jsonify({'status': 405}), 405)


@app.errorhandler(500)
def e500(_):
    return make_response(jsonify({'status': 500}), 500)


def saveFile(jpg: Any, imagePath: str, thumbPath: str):
    logging.log(msg=f"thread image: {imagePath}", level=30)

@app.route('/animation', methods=['POST'])
def postAnimation() -> Response:
    if socket.gethostbyname('bot') != request.remote_addr:
        return e405(0)

    if 'animation' not in request.files:
        return make_response(jsonify({'error': 'No animation'}), 400)
    file = request.files['animation']
    if file:
        hash = hashlib.sha256()
        fb = file.read(65536)
        while len(fb) > 0:
            hash.update(fb)
            fb = file.read(65536)
        file.seek(0)
        hash = hash.hexdigest()[:10]
        name = f"{hash}.mp4"
        file.save(f'/data/{name}')
        response = jsonify({
            'id': hash,
            'link': f"{os.environ.get('BASE_URL')}/animation/{name}",
        })
        response.status_code = 201
        response.autocorrect_location_header = False
        return response
    else:
        return make_response(jsonify({'error': 'No valid mp4 animation'}), 400)



@app.route('/image', methods=['POST'])
def postImage() -> Response:
    if socket.gethostbyname('bot') != request.remote_addr:
        return e405(0)

    if 'image' not in request.files:
        return make_response(jsonify({'error': 'No image'}), 400)
    file = request.files['image']
    if file:
        try:
            hash = hashlib.sha256()
            fb = file.read(65536)
            while len(fb) > 0:
                hash.update(fb)
                fb = file.read(65536)
            hash = hash.hexdigest()[:10]

            imageName = f"{hash}.jpg"
            thumbName = f"{hash}_t.jpg"
            jpg = Image.open(file).convert('RGB')
            width = jpg.width
            height = jpg.height
            jpg.save(f"/data/{imageName}")
            jpg.thumbnail((200, 200))
            jpg.save(f"/data/{thumbName}")

            response = jsonify({
                'id': hash,
                'link': f"{os.environ.get('BASE_URL')}/image/{imageName}",
                'thumb': f"{os.environ.get('BASE_URL')}/image/{thumbName}",
                'width': width,
                'height': height
            })
            response.status_code = 201
            response.autocorrect_location_header = False
            return response
        except IOError as e:
            logging.log(msg=e, level=40)
            return make_response(jsonify({'error': "Cannot parse as image", 'status': 400}), 400)
    return make_response(jsonify({'error': "No image found", 'status': 400}), 400)


@app.route('/image/<file>', methods=['GET'])
@app.route('/animation/<file>', methods=['GET'])
def get(file: str) -> Response:
    return send_from_directory('/data', file)


def deleteOldImages():
    while True:
        logging.log(msg="deleting old images", level=30)

        for item in [p for p in Path('./').glob('*.*') if p.suffix in ['.jpg', '.mp4']]:
            try:
                if item.is_file():
                    itemTime = datetime.fromtimestamp(item.stat().st_mtime)
                    if itemTime < datetime.now() - timedelta(days=2):
                        os.remove(item)
                        logging.log(msg=f"deleted {item}", level=20)
            except:
                pass
        gevent.sleep(60 * 60)

@app.before_first_request
def startClear():
    gevent.spawn(deleteOldImages)

if __name__ == '__main__':
    app.run(debug=True, port=80, host='0.0.0.0')
