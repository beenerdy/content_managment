import os


class ClientNotionDAL:
    def __init__(
        self, client, notion_dal, database_id, drive_dal, vision_service, gemini_service
    ):
        self.client = client
        self.notion_dal = notion_dal
        self.database_id = database_id
        self.drive_dal = drive_dal
        self.vision_service = vision_service
        self.gemini_service = gemini_service

    def generate_captions_for_suggested(self):
        filter_payload = {
            "property": "Status",
            "status": {"equals": "Suggest Captions"},
        }
        # id of: Notion Managed - Active Content
        results = self.notion_dal.query_database(
            "1e8add08074880faa661d372bdb63bce", filter_payload
        )

        for page in results["results"]:
            print(page["properties"]["Status"]["status"]["name"])
            page_id = page["id"]
            properties = page.get("properties", {})

            try:
                image_description = ""
                image_desc_prop = properties.get("Image Description", {}).get(
                    "rich_text", []
                )
                if image_desc_prop:
                    image_description = "".join(
                        [t["plain_text"] for t in image_desc_prop]
                    )

                drive_url = properties["Google Drive File"]["url"]
                file_id = drive_url.split("/d/")[1].split("/")[0]

                smm_relation = properties["Social Media Management"]["relation"]
                if not smm_relation:
                    print(f"Page {page_id} has no SMM relation, skipping.")
                    continue
                smm_page_id = smm_relation[0]["id"]
                prompt, hashtags = self._get_prompt_and_hashtags_from_smm(smm_page_id)

                image_content = self._download_image(file_id)
                if not image_content:
                    print(f"Image content for file {file_id} is empty, skipping.")
                    continue

                labels = self.vision_service.get_labels(image_content)
                caption = self.gemini_service.generate_caption(
                    labels, prompt, hashtags, image_description=image_description
                )

                self.notion_dal.append_blocks(
                    page_id,
                    [
                        {
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {"type": "text", "text": {"content": caption}}
                                ]
                            },
                        }
                    ],
                )
                self.notion_dal.update_page(
                    page_id,
                    properties={"Status": {"status": {"name": "Caption Generated"}}},
                )
                print(f"Processed page {page_id} successfully.")

            except Exception as e:
                import traceback

                print(f"Exception processing page {page_id}: {e}")
                traceback.print_exc()
                continue

    def _download_image(self, file_id):
        """
        Downloads an image file from Google Drive using the file_id.
        Uses the GoogleDriveDAL instance.
        """
        return self.drive_dal.download_file(file_id)

    def _get_prompt_and_hashtags_from_smm(self, smm_page_id):
        """
        Retrieves the prompt and hashtags from the Social Media Management (SMM) page.
        """
        smm_page = self.notion_dal.retrieve_page(smm_page_id)
        hashtags_prop = smm_page["properties"].get("Hashtags", {}).get("rich_text", [])
        hashtags = []
        if hashtags_prop:
            hashtags_text = "".join([t["plain_text"] for t in hashtags_prop])
            hashtags = [h.strip() for h in hashtags_text.split() if h.strip()]

        # Get prompt from first paragraph block (or combine all)
        prompt = ""
        # If you have a method to list blocks:
        blocks = self.notion_dal.notion.blocks.children.list(block_id=smm_page_id)
        for block in blocks.get("results", []):
            if block["type"] == "paragraph" and block["paragraph"]["rich_text"]:
                prompt += block["paragraph"]["rich_text"][0]["text"]["content"] + "\n"
        return prompt.strip(), hashtags

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
        client_notion_id = self.client.get_notion_id("notion_page_id")
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
