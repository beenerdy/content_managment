import re

from notion_client import Client as NotionClient


class NotionDAL:
    def __init__(self, token: str):
        self.notion = NotionClient(auth=token)

    @staticmethod
    def extract_notion_id(url: str) -> str:
        # Remove query params
        url = url.split("?")[0]
        # Find a 32-character hex string at the end of the path
        match = re.search(r"([a-f0-9]{32})$", url.replace("-", ""))
        if match:
            raw = match.group(1)
            return raw  # Return raw ID (no dashes)
        raise ValueError(f"Invalid Notion URL: {url}")

    def get_page_properties(self, page_id: str) -> dict:
        page = self.retrieve_page(page_id)
        return page["properties"]

    def retrieve_page(self, page_id):
        return self.notion.pages.retrieve(page_id)

    def create_page(self, database_id, properties):
        return self.notion.pages.create(
            parent={"database_id": database_id},
            properties=properties,
        )

    def append_blocks(self, page_id, children):
        return self.notion.blocks.children.append(
            block_id=page_id,
            children=children,
        )
