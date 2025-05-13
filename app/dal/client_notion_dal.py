import os


class ClientNotionDAL:
    def __init__(self, client, notion_dal, database_id):
        self.client = client
        self.notion_dal = notion_dal
        self.database_id = database_id

    def get_cycle_start_and_targets(self, smm_page_id):
        page = self.notion_dal.retrieve_page(smm_page_id)
        props = page["properties"]
        cycle_start_str = props.get("Cycle Start Date", {}).get("date", {}).get("start")
        targets = {
            "Photo Posts": props.get("Photo Posts", {}).get("number", 0),
            "Short Videos": props.get("Short Videos", {}).get("number", 0),
            "Long Videos": props.get("Long Videos", {}).get("number", 0),
        }
        return cycle_start_str, targets

    def get_cycle_id_from_social_media_management(self):
        smm_id = self.client.get_notion_id("social_media_managment_id")
        if not smm_id:
            print("No social_media_managment_id found for client.")
            return None
        try:
            page = self.notion_dal.retrieve_page(smm_id)
            properties = page.get("properties", {})
            cycle_id_prop = properties.get("Cycle ID")
            if not cycle_id_prop:
                print(f"'Cycle ID' property not found on SMM page {smm_id}.")
                return None
            if cycle_id_prop["type"] == "rich_text":
                texts = cycle_id_prop["rich_text"]
                if texts:
                    return texts[0]["plain_text"]
            else:
                print(f"Unhandled Cycle ID property type: {cycle_id_prop['type']}")
            return None
        except Exception as e:
            print(f"Failed to fetch Cycle ID from SMM page: {e}")
            return None

    def add_content_grouped(self, file_name, file_id, body_images):
        smm_id = self.client.get_notion_id("social_media_managment_id")
        client_notion_id = self.client.get_notion_id("client_id")
        cycle_id = self.get_cycle_id_from_social_media_management()
        file_base_name = os.path.splitext(file_name)[0]
        identifier = f"{cycle_id} {file_base_name}" if cycle_id else file_base_name

        try:
            file_url = f"https://drive.google.com/file/d/{file_id}/view?usp=drive_web"
            properties = {
                "Identifier": {"title": [{"text": {"content": identifier}}]},
                "Client": {"relation": [{"id": client_notion_id}]},
                "Social Media Management": {"relation": [{"id": smm_id}]},
                "Google Drive File": {"url": file_url},
                "Status": {"status": {"name": "Draft"}},
            }
            page = self.notion_dal.create_page(self.database_id, properties)
            page_id = page["id"]

            children = []
            for file in body_images:
                embed_url = f"https://drive.google.com/file/d/{file['id']}/preview"
                children.append(
                    {"object": "block", "type": "embed", "embed": {"url": embed_url}}
                )
            self.notion_dal.append_blocks(page_id, children)
            print(
                f"Added Notion page for client {self.client.client_name} with Identifier '{identifier}' and embed blocks."
            )
        except Exception as e:
            print(
                f"ERROR: Failed to add to Notion for {self.client.client_name}: {file_name}\n{e}"
            )
