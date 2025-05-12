import json
import os
import re
import sys
import traceback
from collections import defaultdict

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


def parse_file_name(file_name):
    """
    Extracts:
      - group_key: string before first dash (e.g. '2a')
      - num: numeric part of group_key (e.g. '2')
      - letter: letter suffix of group_key, or '' if none (e.g. 'a')
      - match_key: string after first dash, without extension (e.g. '25.03.30-4-COF08133')
    Example:
      '2a-25.03.30-4-COF08133.jpg' -> ('2a', '2', 'a', '25.03.30-4-COF08133')
      '1-25.03.30-7-COF08256.png'  -> ('1',  '1', '',  '25.03.30-7-COF08256')
    """
    m = re.match(r"^([^-]+)-(.+)\.([^.]+)$", file_name)
    if m:
        group_key = m.group(1)
        after_dash = m.group(2)
        num_letter_match = re.match(r"^(\d+)([a-zA-Z]?)$", group_key)
        if num_letter_match:
            num = num_letter_match.group(1)
            letter = num_letter_match.group(2)
            match_key = after_dash
            return group_key, num, letter, match_key
    return None, None, None, None


def move_matching_files(service, fotos_id, scheduling_id, match_key):
    """
    Move files from fotos_id to scheduling_id if their base name matches match_key.
    """
    try:
        # List all files in fotos_id
        fotos_files = (
            service.files()
            .list(
                q=f"'{fotos_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'",
                fields="files(id, name, parents)",
            )
            .execute()
        ).get("files", [])

        # Find matches (base name == match_key)
        found = False
        for file in fotos_files:
            base_name, _ = os.path.splitext(file["name"])
            if base_name == match_key:
                # Move file by updating its parent folder
                service.files().update(
                    fileId=file["id"],
                    addParents=scheduling_id,
                    removeParents=fotos_id,
                    fields="id, parents",
                ).execute()
                print(f"Moved file '{file['name']}' from fotos_id to scheduling_id.")
                found = True
        if not found:
            print(f"File with base name '{match_key}' not found in fotos_id.")
    except Exception as e:
        print(f"ERROR moving file with base name '{match_key}': {e}", file=sys.stderr)


def get_cycle_id_from_social_media_management(social_media_management_id):
    """
    Fetches the Cycle ID property from a Social Media Management page in Notion.
    Returns the Cycle ID as a string, or None if not found.
    """
    if not notion:
        print(
            "ERROR: Notion client not initialized. Cannot fetch Cycle ID.",
            file=sys.stderr,
        )
        return None
    try:
        page = notion.pages.retrieve(social_media_management_id)
        properties = page.get("properties", {})
        cycle_id_prop = properties.get("Cycle ID")
        if not cycle_id_prop:
            print(
                f"WARNING: 'Cycle ID' property not found on Social Media Management page {social_media_management_id}.",
                file=sys.stderr,
            )
            return None
        # Cycle ID is usually a 'rich_text' or 'title' type, handle both
        if cycle_id_prop["type"] == "rich_text":
            texts = cycle_id_prop["rich_text"]
            if texts:
                return texts[0]["plain_text"]
        elif cycle_id_prop["type"] == "title":
            texts = cycle_id_prop["title"]
            if texts:
                return texts[0]["plain_text"]
        elif cycle_id_prop["type"] == "number":
            return str(cycle_id_prop["number"])
        elif cycle_id_prop["type"] == "formula":
            return str(
                cycle_id_prop["formula"].get("string", "")
            )  # if formula returns string
        else:
            print(
                f"WARNING: Unhandled Cycle ID property type: {cycle_id_prop['type']}",
                file=sys.stderr,
            )
        return None
    except Exception as e:
        print(
            f"ERROR: Failed to fetch Cycle ID from Social Media Management page: {e}",
            file=sys.stderr,
        )
        traceback.print_exc()
        return None


def add_content_to_notion_grouped(
    client_id,
    client_name,
    social_media_managment_id,
    client_info,
    file_name,
    file_id,
    body_images,
):
    if not notion:
        print(
            "ERROR: Notion client not initialized. Skipping Notion update.",
            file=sys.stderr,
        )
        return
    client_notion_id = client_info["notion"]["client_id"]

    # --- Fetch Cycle ID for Identifier ---
    cycle_id = get_cycle_id_from_social_media_management(social_media_managment_id)
    identifier = ""
    file_base_name = os.path.splitext(file_name)[0]
    if cycle_id:
        identifier = f"{cycle_id} {file_base_name}"
    else:
        identifier = file_base_name  # fallback if Cycle ID not found

    try:
        file_url = f"https://drive.google.com/file/d/{file_id}/view?usp=drive_web"
        # 1. Create the page with properties (including the URL property)
        page = notion.pages.create(
            parent={"database_id": NOTION_DB_ID},
            properties={
                "Identifier": {"title": [{"text": {"content": identifier}}]},
                "Client": {"relation": [{"id": client_id}]},
                "Social Media Management": {
                    "relation": [{"id": social_media_managment_id}]
                },
                "Google Drive File": {"url": file_url},  # URL property
                "Status": {"status": {"name": "Draft"}},
                "Client": {"relation": [{"id": client_notion_id}]},
            },
        )
        page_id = page["id"]

        # 2. Append embed blocks for all images in body_images
        children = []
        for file in body_images:
            embed_url = f"https://drive.google.com/file/d/{file['id']}/preview"
            children.append(
                {"object": "block", "type": "embed", "embed": {"url": embed_url}}
            )
        notion.blocks.children.append(
            block_id=page_id,
            children=children,
        )

        print(
            f"Added Notion page for client {client_name} with Identifier '{identifier}' and embed blocks."
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
        client_id = client_info["notion"]["client_id"]
        social_media_managment_id = client_info["notion"]["social_media_managment_id"]
        client_name = client_info["client_name"]
        folder_id = client_info["google_drive"]["next_post_id"]
        fotos_id = client_info["google_drive"]["fotos_id"]
        scheduling_id = client_info["google_drive"]["scheduling_id"]

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

        # --- Group files by main number ---
        groups = defaultdict(list)
        file_lookup = {}
        for file in files:
            file_name = file["name"]
            group_key, num, letter, match_key = parse_file_name(file_name)
            if num is None:
                print(
                    f"WARNING: File '{file_name}' does not match expected pattern, skipping.",
                    file=sys.stderr,
                )
                continue

            # Move matching files from fotos_id to scheduling_id
            move_matching_files(service, fotos_id, scheduling_id, match_key)
            groups[num].append((letter, file))
            file_lookup[file_name] = file

        # --- Sort groups by number, and each group by letter (main image first, then secondaries) ---
        sorted_group_keys = sorted(groups.keys(), key=lambda x: int(x))
        last_number = 0
        for group_num in sorted_group_keys:
            try:
                curr_number = int(group_num)
                # Strict order check
                if curr_number != last_number + 1:
                    print(
                        f"ERROR: Missing main image for expected number {last_number + 1}.",
                        file=sys.stderr,
                    )
                last_number = curr_number

                group_files = sorted(
                    groups[group_num], key=lambda x: (x[0] == "", x[0])
                )  # Main image ('') first
                main_image = next((f for l, f in group_files if l == ""), None)
                if not main_image:
                    # There are only secondary images for this number
                    for letter, file in group_files:
                        file_name = file["name"]
                        print(
                            f"ERROR: Secondary image {file_name} found but main image {group_num} is missing.",
                            file=sys.stderr,
                        )
                    continue

                # Main image exists, process group
                file_id = main_image["id"]
                file_name = main_image["name"]

                make_drive_file_public(service, file_id)

                # Prepare all images for body: main first, then secondaries (sorted by letter)
                body_images = []
                # Main image first
                body_images.append(main_image)
                # Then secondaries, sorted by letter
                for letter, file in sorted(
                    group_files, key=lambda x: (x[0] == "", x[0])
                ):
                    if letter != "":
                        print(f"Adding secondary image to body: {file['name']}")
                        body_images.append(file)

                # Add to Notion
                add_content_to_notion_grouped(
                    client_id,
                    client_name,
                    social_media_managment_id,
                    client_info,
                    file_name,
                    file_id,
                    body_images,
                )

            except Exception as e:
                print(
                    f"ERROR: Failed processing group {group_num}: {e}",
                    file=sys.stderr,
                )
                traceback.print_exc()
                continue

        return ("", 200)
    except Exception as e:
        print(f"FATAL ERROR in webhook handler: {e}", file=sys.stderr)
        traceback.print_exc()
        return ("", 500)
