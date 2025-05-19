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

    def update_page(self, page_id, properties):
        """
        Update properties of a Notion page.
        :param page_id: The Notion page ID.
        :param properties: Dict of properties to update.
        :return: The API response (dict) with the updated page.
        """
        return self.notion.pages.update(
            page_id=page_id,
            properties=properties,
        )

    def append_blocks(self, page_id, children):
        return self.notion.blocks.children.append(
            block_id=page_id,
            children=children,
        )

    def query_database(self, database_id, filter_payload):
        """
        Query a Notion database using a filter.
        :param database_id: The Notion database ID.
        :param filter_payload: A dict representing the Notion filter.
        :return: The API response (dict) containing the results.
        """
        return self.notion.databases.query(
            database_id=database_id, filter=filter_payload
        )
