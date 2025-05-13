from dal.google_drive_dal import GoogleDriveDAL
from dal.notion_dal import NotionDAL
from models.client import Client
from models.client_map import ClientMap


class ClientManager:
    notion_dal = None
    drive_dal = None
    client_map = None

    @classmethod
    def init(cls, notion_token, google_service_account, client_map_path):
        from dal.google_drive_dal import GoogleDriveDAL
        from dal.notion_dal import NotionDAL
        from models.client_map import ClientMap

        cls.notion_dal = NotionDAL(notion_token)
        cls.drive_dal = GoogleDriveDAL(google_service_account)
        cls.client_map = ClientMap()
        cls.client_map.load_from_file(client_map_path)

    @classmethod
    def create_client_from_payload(cls, payload):
        notion_url = payload.get("notion_url")
        if not notion_url:
            raise ValueError("Missing 'notion_url'")

        page_id = cls.notion_dal.extract_notion_id(notion_url)
        client = Client.from_notion(cls.notion_dal, page_id, uuid=page_id)

        for resource in payload.get("google_drive", []):
            key = resource.get("key")
            url = resource.get("url")
            description = resource.get("description", "")
            if not key or not url:
                continue
            folder_id = cls.drive_dal.extract_folder_id(url)
            client.add_resource("google_drive", key, folder_id, description, url)

        for resource in payload.get("notion", []):
            key = resource.get("key")
            url = resource.get("url")
            description = resource.get("description", "")
            if not key or not url:
                continue
            notion_id = cls.notion_dal.extract_notion_id(url)
            client.add_resource("notion", key, notion_id, description, url)

        cls.client_map.add_client(client)
        cls.client_map.save_to_file("client_map.json")
        return client
