import logging
import os
from flask import Flask, request, jsonify
from flask.helpers import make_response, send_from_directory
from flask.wrappers import Response
import hashlib
from PIL import Image
import socket

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

@app.route('/image', methods=['POST'])
def post() -> Response:
  if socket.gethostbyname('app') != request.remote_addr:
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
      jpg.save(f"/data/{imageName}")
      jpg.thumbnail((200, 200))
      jpg.save(f"/data/{thumbName}")
      response = jsonify({
        'id': hash,
        'link': f"{os.environ.get('BASE_URL')}/image/{imageName}",
        'thumb': f"{os.environ.get('BASE_URL')}/image/{thumbName}",
        })
      response.status_code = 201
      response.autocorrect_location_header = False
      return response
    except IOError as e:
      logging.log(msg=e, level=40)
      return make_response(jsonify({'error': "Cannot parse as image", 'status': 400}), 400)
  return make_response(jsonify({'error': "No image found", 'status': 400}), 400)

@app.route('/image/<file>', methods=['GET'])
def get(file: str) -> Response:
  logging.log(msg=f"{socket.gethostbyname('app')}: {request.remote_addr}", level=40)
  return send_from_directory('/data', file)

if __name__ == '__main__':
    app.run(debug=True, port=80, host='0.0.0.0')
