import os

from dal.google_drive_dal import GoogleDriveDAL
from dal.notion_dal import NotionDAL
from dal.todoist_dal import TodoistDAL
from flask import Flask
from managers.client_manager import ClientManager
from models.client_map import ClientMap


def create_app():
    app = Flask(__name__)

    # Load config (from environment or a config file)
    app.config["CLIENT_MAP_PATH"] = os.environ.get("CLIENT_MAP_PATH", "client_map.json")
    app.config["NOTION_TOKEN"] = os.environ.get("NOTION_TOKEN")
    app.config["TODOIST_TOKEN"] = os.environ.get("TODOIST_TOKEN")
    app.config["SERVICE_ACCOUNT_FILE"] = os.environ.get(
        "SERVICE_ACCOUNT_FILE", "service-account.json"
    )
    app.config["CONTENT_DB_NOTION_ID"] = os.environ.get(
        "CONTENT_DB_NOTION_ID", "1e8add08074880faa661d372bdb63bce"
    )

    # Initialise shared resources
    client_map = ClientMap()
    client_map.load_from_file(app.config["CLIENT_MAP_PATH"])
    drive_dal = GoogleDriveDAL(app.config["SERVICE_ACCOUNT_FILE"])
    notion_dal = NotionDAL(app.config["NOTION_TOKEN"])
    todoist_dal = TodoistDAL(app.config["TODOIST_TOKEN"])
    client_manager = ClientManager(
        client_map, drive_dal, notion_dal, app.config["CONTENT_DB_NOTION_ID"]
    )

    # Attach to app for access in routes
    app.client_map = client_map
    app.drive_dal = drive_dal
    app.notion_dal = notion_dal
    app.todoist_dal = todoist_dal
    app.client_manager = client_manager

    # Register routes (directly or via blueprints)
    from routes import register_routes

    register_routes(app)

    return app
