from flask import Flask, request

import generate_caption
import webhook_handler

app = Flask(__name__)


@app.route("/drive-webhook", methods=["POST"])
def local_drive_webhook():
    return webhook_handler.drive_webhook(request)


@app.route("/generate-caption", methods=["POST"])
def local_generate_caption():
    return generate_caption.generate_caption_handler(request)


if __name__ == "__main__":
    app.run(port=8080, debug=True)
