from flask import Flask, jsonify, request

import generate_caption
import webhook_handler
from collect_captions import get_captions_for_client

app = Flask(__name__)


@app.route("/drive-webhook", methods=["POST"])
def local_drive_webhook():
    return webhook_handler.drive_webhook(request)


@app.route("/generate-caption", methods=["POST"])
def local_generate_caption():
    return generate_caption.generate_caption_handler(request)


@app.route("/collect-captions", methods=["GET"])
def collect_captions_route():
    client_name = request.args.get("client_name")
    if not client_name:
        return jsonify({"error": "Missing 'client_name' parameter"}), 400

    message, error = get_captions_for_client(client_name)
    if error:
        return jsonify({"error": error}), 400
    return message, 200


if __name__ == "__main__":
    app.run(port=8082, debug=True)


if __name__ == "__main__":
    app.run(port=8080, debug=True)
