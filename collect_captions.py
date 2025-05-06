import json
import os
import sys
import traceback

from notion_client import Client as NotionClient
from notion_client.errors import APIResponseError

CLIENT_MAP_FILE = "client_map.json"
if not os.path.exists(CLIENT_MAP_FILE):
    print(f"ERROR: {CLIENT_MAP_FILE} does not exist.", file=sys.stderr)
    CLIENT_MAP = {}
else:
    with open(CLIENT_MAP_FILE) as f:
        try:
            CLIENT_MAP = json.load(f)
        except Exception as e:
            print(f"ERROR: Failed to load {CLIENT_MAP_FILE}: {e}", file=sys.stderr)
            CLIENT_MAP = {}

NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_DB_ID = "1e8add08074880faa661d372bdb63bce"  # Update if needed

notion = NotionClient(auth=NOTION_TOKEN) if NOTION_TOKEN else None


def get_cycle_id_from_social_media_management(social_media_management_id):
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


def get_client_info_by_name(client_name):
    for k, v in CLIENT_MAP.items():
        if v.get("client_name") == client_name:
            return v
    return None


def get_captions_for_client(client_name):
    if not notion:
        return None, "Notion client not initialized."
    client_info = get_client_info_by_name(client_name)
    if not client_info:
        return None, f"Client '{client_name}' not found in client_map.json"
    social_media_management_id = client_info["notion"].get("social_media_managment_id")
    if not social_media_management_id:
        return None, f"Social Media Management ID not found for client '{client_name}'"
    cycle_id = get_cycle_id_from_social_media_management(social_media_management_id)
    if not cycle_id:
        return None, f"Cycle ID not found for client '{client_name}'"

    identifier_prefix = f"{cycle_id} "
    try:
        results = notion.databases.query(
            **{
                "database_id": NOTION_DB_ID,
                "filter": {
                    "and": [
                        {
                            "property": "Status",
                            "status": {"equals": "Caption Generated"},
                        },
                        {
                            "property": "Identifier",
                            "title": {"starts_with": identifier_prefix},
                        },
                    ]
                },
                "page_size": 100,
            }
        )
        items = results.get("results", [])
        posts = []
        for page in items:
            props = page.get("properties", {})
            identifier_prop = props.get("Identifier", {})
            number = None
            if identifier_prop.get("type") == "title":
                title_objs = identifier_prop.get("title", [])
                if title_objs:
                    identifier_text = title_objs[0].get("plain_text", "")
                    if identifier_text.startswith(identifier_prefix):
                        try:
                            number = int(
                                identifier_text[len(identifier_prefix) :].strip()
                            )
                        except ValueError:
                            print(
                                f"WARNING: Could not parse number from Identifier: '{identifier_text}'",
                                file=sys.stderr,
                            )
            if number is not None:
                posts.append((number, identifier_text))
        if not posts:
            return "", f"No posts found for cycle '{cycle_id}'."

        # Sort posts by number
        posts.sort(key=lambda x: x[0])

        # Check for missing numbers and build the bullet point message
        numbers = [num for num, _ in posts]
        min_num = min(numbers)
        max_num = max(numbers)
        message_lines = []
        for expected_num in range(min_num, max_num + 1):
            match = next((idtext for num, idtext in posts if num == expected_num), None)
            if match is None:
                print(
                    f"ERROR: Missing post {expected_num} in cycle '{cycle_id}'.",
                    file=sys.stderr,
                )
                continue
            message_lines.append(f"- ({expected_num})")
        message = "\n".join(message_lines)
        return message, None
    except APIResponseError as e:
        print(f"ERROR: Notion API error: {e}", file=sys.stderr)
        traceback.print_exc()
        return None, f"Notion API error: {e}"
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}", file=sys.stderr)
        traceback.print_exc()
        return None, f"Unexpected error: {e}"
