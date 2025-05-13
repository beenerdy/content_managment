from dataclasses import asdict, dataclass, field
from typing import Dict, Optional


@dataclass
class ResourceEntry:
    id: str
    description: str
    url: str


@dataclass
class Client:
    uuid: str
    tag: str
    client_name: str
    notion_page_id: str
    google_drive: Dict[str, ResourceEntry] = field(default_factory=dict)
    notion: Dict[str, ResourceEntry] = field(default_factory=dict)

    @classmethod
    def from_notion(cls, notion_dal, page_id: str, uuid: str = None):
        """
        Create a Client from Notion page properties.
        """
        properties = notion_dal.get_page_properties(page_id)

        def get_text(prop):
            if prop.get("title"):
                return "".join([t["plain_text"] for t in prop["title"]])
            if prop.get("rich_text"):
                return "".join([t["plain_text"] for t in prop["rich_text"]])
            return ""

        client_name = get_text(properties.get("Project name", {}))
        tag = get_text(properties.get("Tags", {}))

        return cls(uuid=uuid, tag=tag, client_name=client_name, notion_page_id=page_id)

    def add_resource(self, service: str, key: str, id: str, description: str, url: str):
        entry = ResourceEntry(id=id, description=description, url=url)
        if service == "google_drive":
            self.google_drive[key] = entry
        elif service == "notion":
            self.notion[key] = entry
        else:
            raise ValueError("Unknown service")

    def get_resource(self, service: str, key: str) -> Optional[ResourceEntry]:
        if service == "google_drive":
            return self.google_drive.get(key)
        elif service == "notion":
            return self.notion.get(key)
        return None

    def to_dict(self) -> dict:
        return {
            "tag": self.tag,
            "client_name": self.client_name,
            "notion_page_id": self.notion_page_id,
            "google_drive": {k: asdict(v) for k, v in self.google_drive.items()},
            "notion": {k: asdict(v) for k, v in self.notion.items()},
        }

    @staticmethod
    def from_dict(uuid: str, data: dict) -> "Client":
        gd = {k: ResourceEntry(**v) for k, v in data.get("google_drive", {}).items()}
        nt = {k: ResourceEntry(**v) for k, v in data.get("notion", {}).items()}
        return Client(
            uuid=uuid,
            tag=data.get("tag", ""),
            client_name=data.get("client_name", ""),
            notion_page_id=data.get("notion_page_id", uuid),  # <-- Default to uuid
            google_drive=gd,
            notion=nt,
        )
