import os
import uuid

from dal.google_drive_dal import GoogleDriveDAL
from dal.notion_dal import NotionDAL
from flask import Flask, jsonify, request
from managers.client_manager import ClientManager
from models.client import Client
from models.client_map import ClientMap

CLIENT_MAP_PATH = "client_map.json"
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
SERVICE_ACCOUNT_FILE = "service-account.json"

app = Flask(__name__)

client_map = ClientMap()
client_map.load_from_file(CLIENT_MAP_PATH)


@app.route("/client/<client_uuid>/add_id", methods=["POST"])
def add_id(client_uuid):
    data = request.json
    service = data.get("service")
    key = data.get("key")
    url = data.get("url")
    description = data.get("description")

    if not all([service, key, url, description]):
        return jsonify({"error": "Missing required fields"}), 400

    client = client_map.get_client(client_uuid)
    if not client:
        return jsonify({"error": f"Client UUID {client_uuid} not found."}), 404

    try:
        if service == "google_drive":
            id_value = GoogleDriveDAL.extract_folder_id(url)
        elif service == "notion":
            id_value = NotionDAL.extract_notion_id(url)
        else:
            return (
                jsonify({"error": "Service must be 'google_drive' or 'notion'."}),
                400,
            )

        client.add_resource(service, key, id_value, description)
        client_map.save_to_file(CLIENT_MAP_PATH)
        return jsonify({"message": "ID added successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/client_map", methods=["GET"])
def get_client_map():
    return jsonify(client_map.to_dict())


@app.route("/client", methods=["POST"])
def create_client_from_notion():
    ClientManager.init(NOTION_TOKEN, SERVICE_ACCOUNT_FILE, CLIENT_MAP_PATH)
    data = request.json
    try:
        client = ClientManager.create_client_from_payload(data)
        return (
            jsonify(
                {
                    "uuid": client.uuid,
                    "message": "Client created",
                    "client": client.to_dict(),
                }
            ),
            201,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    app.run(debug=True)
