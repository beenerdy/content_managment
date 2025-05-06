import json
import uuid
from collections import defaultdict

from google.oauth2 import service_account
from googleapiclient.discovery import build

SERVICE_ACCOUNT_FILE = "service-account.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]
ACTIVE_CLIENTI_FOLDER_ID = "17J-K2F1ktUOgx_UK7rRffw1xTgFSEf37"
CLIENT_MAP_FILE = "client_map.json"


def get_service_account_email():
    with open(SERVICE_ACCOUNT_FILE) as f:
        client_email = json.load(f)["client_email"]
        print(f"Client email fetching the folders {client_email}")
        return client_email


def check_folder_permissions(
    service, folder_id, service_account_email, folder_label=""
):
    permissions = (
        service.permissions()
        .list(fileId=folder_id, fields="permissions(emailAddress,role,type)")
        .execute()
    )
    found = False
    print(f"\nPermissions for {folder_label or folder_id}:")
    for perm in permissions.get("permissions", []):
        who = perm.get("emailAddress", perm.get("type"))
        print(f"  {who}: {perm['role']}")
        if who == service_account_email:
            found = True
    if not found:
        print(
            f"  ⚠️  Service account {service_account_email} NOT FOUND in permissions for {folder_label or folder_id}!"
        )
    return found


def get_subfolder_id(service, parent_id, folder_name):
    query = (
        f"'{parent_id}' in parents and "
        f"name = '{folder_name}' and "
        f"mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None


def list_clients(service, active_clienti_folder_id):
    query = (
        f"'{active_clienti_folder_id}' in parents and "
        f"mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    return [(f["name"], f["id"]) for f in files]


def main():
    service_account_email = get_service_account_email()
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    service = build("drive", "v3", credentials=creds)

    # Check permissions on the parent "0. Active Clienti" folder
    check_folder_permissions(
        service,
        ACTIVE_CLIENTI_FOLDER_ID,
        service_account_email,
        folder_label="0. Active Clienti",
    )

    clients = list_clients(service, ACTIVE_CLIENTI_FOLDER_ID)
    if not clients:
        print("No client folders found. Please check permissions and folder structure.")
        return

    client_map = defaultdict(lambda: defaultdict(dict))

    for client_name, client_id in clients:
        # Only add client if not already present (by client_name)
        already_present = any(
            entry.get("client_name") == client_name for entry in client_map.values()
        )
        if already_present:
            print(f"  ➡️  Skipping existing client: {client_name}")
            continue

        planner_id = get_subfolder_id(service, client_id, "0. Planner")
        if not planner_id:
            print(f"  ❌ Missing '0. Planner' for {client_name}")
            continue

        next_post_id = get_subfolder_id(service, planner_id, "1. Next Posts")
        if not next_post_id:
            print(f"  ❌ Missing '1. Next Posts' for {client_name}")
            continue

        # Prompt user for Notion client_id
        notion_client_id = input(
            f"Enter Notion client_id for '{client_name}': "
        ).strip()

        social_media_managment_id = input(
            f"Enter Notion client_id for '{client_name}': "
        ).strip()

        # Generate a UUID for the channel
        channel_uuid = str(uuid.uuid4())

        client_map[channel_uuid] = {
            "client_name": client_name,
            "google_drive": {"next_post_id": next_post_id},
            "notion": {
                "client_id": notion_client_id,
                "social_media_managment_id": social_media_managment_id,
            },
        }

        print(f"  ✅ Added {client_name} with channel UUID {channel_uuid}")

    with open(CLIENT_MAP_FILE, "w") as f:
        json.dump(client_map, f, indent=2)

    print("\nDone! Updated client_map.json")
    print(
        "If you saw any warnings above, please share the relevant folders with your service account."
    )


if __name__ == "__main__":
    main()
