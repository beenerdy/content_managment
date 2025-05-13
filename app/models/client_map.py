import json
from typing import Dict, Optional

from models.client import Client


class ClientMap:
    def __init__(self):
        self.clients: Dict[str, Client] = {}

    def load_from_file(self, path: str):
        try:
            with open(path, "r") as f:
                data = json.load(f)
                for uuid, client_data in data.items():
                    self.clients[uuid] = Client.from_dict(uuid, client_data)
        except FileNotFoundError:
            self.clients = {}

    def save_to_file(self, path: str):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    def get_client(self, uuid: str) -> Optional[Client]:
        return self.clients.get(uuid)

    def add_client(self, client: Client):
        self.clients[client.uuid] = client

    @staticmethod
    def from_dict(uuid: str, data: dict) -> "Client":
        gd = {k: ResourceEntry(**v) for k, v in data.get("google_drive", {}).items()}
        nt = {k: ResourceEntry(**v) for k, v in data.get("notion", {}).items()}
        return Client(
            uuid=uuid,
            tag=data.get("tag", ""),
            client_name=data.get("client_name", ""),
            notion_page_id=data.get("notion_page_id", uuid),
            notion_url=data.get("notion_url", ""),
            google_drive=gd,
            notion=nt,
        )

    def to_dict(self) -> dict:
        return {uuid: client.to_dict() for uuid, client in self.clients.items()}
