import json
import os
import sys
import traceback

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from notion_client import Client as NotionClient
from notion_client.errors import APIResponseError

# --- Load channel map at module load ---
CLIENT_MAP_FILE = "client_map.json"
if not os.path.exists(CLIENT_MAP_FILE):
    print(f"ERROR: {CLIENT_MAP_FILE} does not exist.", file=sys.stderr)
    CHANNEL_MAP = {}
else:
    with open(CLIENT_MAP_FILE) as f:
        try:
            CHANNEL_MAP = json.load(f)
        except Exception as e:
            print(f"ERROR: Failed to load {CLIENT_MAP_FILE}: {e}", file=sys.stderr)
            CHANNEL_MAP = {}

SERVICE_ACCOUNT_FILE = "service-account.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

NOTION_TOKEN = os.environ.get("NOTION_TOKEN")  # Set as env var for deployment
NOTION_DB_ID = "1e8add08074880faa661d372bdb63bce"  # Your Notion database ID

if not NOTION_TOKEN:
    print("ERROR: NOTION_TOKEN environment variable not set.", file=sys.stderr)
    notion = None
else:
    notion = NotionClient(auth=NOTION_TOKEN)


def get_service():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"ERROR: {SERVICE_ACCOUNT_FILE} does not exist.", file=sys.stderr)
        return None
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        print(f"ERROR: Failed to create Google Drive service: {e}", file=sys.stderr)
        traceback.print_exc()
        return None


def make_drive_file_public(service, file_id):
    try:
        service.permissions().create(
            fileId=file_id, body={"role": "reader", "type": "anyone"}, fields="id"
        ).execute()
        print(f"Made file {file_id} public.")
    except Exception as e:
        print(f"Could not make file public: {e}")


def add_content_to_notion(client_name, client_info, file_name, file_id):
    if not notion:
        print(
            "ERROR: Notion client not initialized. Skipping Notion update.",
            file=sys.stderr,
        )
        return
    client_notion_id = client_info["notion"]["client_id"]
    try:
        file_url = f"https://drive.google.com/file/d/{file_id}/view?usp=drive_web"
        embed_url = f"https://drive.google.com/file/d/{file_id}/preview"
        # 1. Create the page with properties (including the URL property)
        page = notion.pages.create(
            parent={"database_id": NOTION_DB_ID},
            properties={
                "Caption": {"title": [{"text": {"content": ""}}]},
                "Google Drive File": {"url": file_url},  # URL property
                "Status": {"status": {"name": "Draft"}},
                "Client": {"relation": [{"id": client_notion_id}]},
            },
        )
        page_id = page["id"]

        # 2. Append an embed block with the Google Drive preview link
        notion.blocks.children.append(
            block_id=page_id,
            children=[
                {"object": "block", "type": "embed", "embed": {"url": embed_url}}
            ],
        )

        print(
            f"Added Notion page for client {client_name} with Google Drive URL and embed block."
        )
    except APIResponseError as e:
        print(
            f"ERROR: Failed to add to Notion for {client_name}: {file_name}\n{e}",
            file=sys.stderr,
        )
    except Exception as e:
        print(f"ERROR: Unexpected error adding to Notion: {e}", file=sys.stderr)
        traceback.print_exc()


def drive_webhook(request):
    try:
        channel_id = request.headers.get("X-Goog-Channel-ID")
        resource_state = request.headers.get("X-Goog-Resource-State")
        print(f"Webhook received: channel={channel_id}, state={resource_state}")

        if not channel_id:
            print("ERROR: Missing X-Goog-Channel-ID header.", file=sys.stderr)
            return ("", 400)
        if not resource_state:
            print("ERROR: Missing X-Goog-Resource-State header.", file=sys.stderr)
            return ("", 400)

        if channel_id not in CHANNEL_MAP:
            print(f"Ignoring event: unknown channel ID {channel_id}")
            return ("", 200)

        client_info = CHANNEL_MAP[channel_id]
        client_name = client_info["client_name"]
        folder_id = client_info["google_drive"]["next_post_id"]

        # Only process if this is an 'add' or 'change' event
        if resource_state not in ["add", "change"]:
            print(f"Ignoring event: resource_state '{resource_state}' not actionable.")
            return ("", 200)

        service = get_service()
        if not service:
            print("ERROR: Google Drive service not available.", file=sys.stderr)
            return ("", 500)

        try:
            results = (
                service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'",
                    fields="files(id, name, createdTime, parents)",
                )
                .execute()
            )
            files = results.get("files", [])
        except HttpError as e:
            print(f"ERROR: Google Drive API error: {e}", file=sys.stderr)
            traceback.print_exc()
            return ("", 500)
        except Exception as e:
            print(f"ERROR: Unexpected error listing files: {e}", file=sys.stderr)
            traceback.print_exc()
            return ("", 500)

        if not files:
            print(f"No files found in folder {folder_id} for client {client_name}.")
            return ("", 200)

        for file in files:
            try:
                file_id = file["id"]
                file_name = file["name"]

                make_drive_file_public(service, file_id)
                add_content_to_notion(client_name, client_info, file_name, file_id)

            except Exception as e:
                print(
                    f"ERROR: Failed processing file {file.get('id', '')}: {e}",
                    file=sys.stderr,
                )
                traceback.print_exc()
                continue

        return ("", 200)
    except Exception as e:
        print(f"FATAL ERROR in webhook handler: {e}", file=sys.stderr)
        traceback.print_exc()
        return ("", 500)
