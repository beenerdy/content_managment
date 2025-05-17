from datetime import datetime, timedelta

from dal.client_drive_dal import ClientDriveDAL
from dal.client_notion_dal import ClientNotionDAL
from dal.google_drive_dal import GoogleDriveDAL
from dal.notion_dal import NotionDAL
from models.client import Client
from models.client_map import ClientMap


class ClientManager:
    def __init__(self, client_map, drive_dal, notion_dal, notion_db_id):
        self.client_map = client_map
        self.drive_dal = drive_dal
        self.notion_dal = notion_dal
        self.notion_db_id = notion_db_id

    def create_client_from_payload(self, payload):
        notion_url = payload.get("notion_url")
        if not notion_url:
            raise ValueError("Missing 'notion_url'")

        page_id = self.notion_dal.extract_notion_id(notion_url)
        print(notion_url, page_id)
        client = Client.from_notion(
            self.notion_dal, page_id, uuid=page_id, notion_url=notion_url
        )

        for resource in payload.get("google_drive", []):
            key = resource.get("key")
            url = resource.get("url")
            description = resource.get("description", "")
            if not key or not url:
                continue
            folder_id = self.drive_dal.extract_folder_id(url)
            client.add_resource("google_drive", key, folder_id, description, url)

        for resource in payload.get("notion", []):
            key = resource.get("key")
            url = resource.get("url")
            description = resource.get("description", "")
            if not key or not url:
                continue
            notion_id = self.notion_dal.extract_notion_id(url)
            client.add_resource("notion", key, notion_id, description, url)

        self.client_map.add_client(client)
        self.client_map.save_to_file("client_map.json")
        return client

    def ensure_content_buffer(self, todoist_dal, today=None):
        today = today or datetime.now().date()

        for client in self.client_map.clients.values():
            smm_id = client.get_notion_id("social_media_managment_id")
            if not smm_id:
                continue
            notion = ClientNotionDAL(client, self.notion_dal, self.notion_db_id)
            cycle_start_str, targets = notion.get_cycle_start_and_targets(smm_id)
            if not cycle_start_str:
                print(f"Cycle Start Date not set for client {client.client_name}")
                continue
            cycle_start = datetime.fromisoformat(cycle_start_str).date()

            buffer_deadline, week_in_cycle, cycle_num = self.get_next_buffer_deadline(
                today, cycle_start
            )
            if buffer_deadline is None:
                print(f"Could not determine buffer deadline for {client.client_name}")
                continue

            print(
                f"Checking buffer for {client.client_name}: week {week_in_cycle}, buffer deadline {buffer_deadline}"
            )

            drive = ClientDriveDAL(client, self.drive_dal)
            type_map = {
                "Photo Posts": "photos",
                "Short Videos": "short_videos",
                "Long Videos": "long_videos",
            }

            for content_type, target in targets.items():
                canonical_type = type_map[content_type]
                base_per_week = target // 4
                remainder = target % 4
                content_target = base_per_week + (
                    1 if week_in_cycle <= remainder else 0
                )
                ready_count = drive.count_ready_files(canonical_type)

                if ready_count < content_target:
                    identifier = f"Buffer check cycle {cycle_num} week {week_in_cycle} {client.client_name} {content_type}"
                    if not todoist_dal.task_exists(identifier):
                        content = (
                            f"[{identifier}] Prepare more {content_type.lower()} for "
                            f"{client.client_name} (need {content_target}, have {ready_count})"
                        )
                        due_string = buffer_deadline.strftime("%Y-%m-%d")
                        todoist_dal.create_task(content, due_string=due_string)
                        print(f"Created Todoist task: {content}")

    def sync_next_posts_from_drive_to_notion(self, channel_id):
        client = self.client_map.get_client(channel_id)

        drive = ClientDriveDAL(client, self.drive_dal)
        notion = ClientNotionDAL(client, self.notion_dal, self.notion_db_id)

        files = drive.list_next_posts()
        if not files:
            print(f"No files found in next_post_id for client {client.client_name}.")
            return

        from collections import defaultdict

        groups = defaultdict(list)
        for file in files:
            file_name = file["name"]
            group_key, num, letter, match_key = drive.parse_file_name(file_name)
            if num is None:
                print(
                    f"WARNING: File '{file_name}' does not match expected pattern, skipping."
                )
                continue
            if match_key:  # Only move if match_key is not empty
                drive.move_matching_files(match_key)
            groups[num].append((letter, file))

        sorted_group_keys = sorted(groups.keys(), key=lambda x: int(x))
        last_number = 0
        for group_num in sorted_group_keys:
            try:
                curr_number = int(group_num)
                if curr_number != last_number + 1:
                    print(
                        f"ERROR: Missing main image for expected number {last_number + 1}."
                    )
                last_number = curr_number

                group_files = sorted(
                    groups[group_num], key=lambda x: (x[0] == "", x[0])
                )
                main_image = next((f for l, f in group_files if l == ""), None)
                if not main_image:
                    for letter, file in group_files:
                        print(
                            f"ERROR: Secondary image {file['name']} found but main image {group_num} is missing."
                        )
                    continue

                file_id = main_image["id"]
                file_name = main_image["name"]
                drive.make_file_public(file_id)

                body_images = [main_image]
                for letter, file in sorted(
                    group_files, key=lambda x: (x[0] == "", x[0])
                ):
                    if letter != "":
                        print(f"Adding secondary image to body: {file['name']}")
                        body_images.append(file)

                notion.add_content_grouped(file_name, file_id, body_images)
            except Exception as e:
                print(f"ERROR: Failed processing group {group_num}: {e}")
                continue

    def get_next_buffer_deadline(self, today, cycle_start):
        # Find the next Monday after today
        days_until_next_monday = (7 - today.weekday()) % 7
        next_week_start = today + timedelta(days=days_until_next_monday)
        if next_week_start < cycle_start:
            next_week_start = cycle_start
        days_since_cycle = (next_week_start - cycle_start).days
        weeks_since_cycle = days_since_cycle // 7
        cycle_num = weeks_since_cycle // 4 + 1
        week_in_cycle = weeks_since_cycle % 4 + 1

        # Buffer deadline is the previous Wednesday before next_week_start
        buffer_deadline = self.previous_wednesday(next_week_start)
        return buffer_deadline, week_in_cycle, cycle_num

    def previous_wednesday(self, before_date):
        days_back = (before_date.weekday() - 2) % 7 or 7  # Wednesday is 2
        return before_date - timedelta(days=days_back)
