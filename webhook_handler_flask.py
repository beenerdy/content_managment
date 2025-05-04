from flask import Flask, request

import webhook_handler

app = Flask(__name__)


@app.route("/drive-webhook", methods=["POST"])
def local_drive_webhook():
    return webhook_handler.drive_webhook(request)


if __name__ == "__main__":
    app.run(port=8080, debug=True)
