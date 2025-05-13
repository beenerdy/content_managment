import json
import re
from typing import List, Optional, Tuple

from google.oauth2 import service_account
from googleapiclient.discovery import build


class GoogleDriveDAL:
    SCOPES = ["https://www.googleapis.com/auth/drive"]

    def __init__(self, service_account_file: str):
        self.creds = service_account.Credentials.from_service_account_file(
            service_account_file, scopes=self.SCOPES
        )
        self.service = build("drive", "v3", credentials=self.creds)
        self.service_account_email = self._get_service_account_email(
            service_account_file
        )

    @staticmethod
    def extract_folder_id(url: str) -> str:
        match = re.search(r"/folders/([a-zA-Z0-9_-]+)", url)
        if not match:
            raise ValueError(f"Invalid Google Drive folder URL: {url}")
        return match.group(1)

    @staticmethod
    def _get_service_account_email(service_account_file: str) -> str:
        with open(service_account_file) as f:
            return json.load(f)["client_email"]

    def check_folder_permissions(self, folder_id: str, folder_label: str = "") -> bool:
        permissions = (
            self.service.permissions()
            .list(fileId=folder_id, fields="permissions(emailAddress,role,type)")
            .execute()
        )
        found = False
        for perm in permissions.get("permissions", []):
            who = perm.get("emailAddress", perm.get("type"))
            if who == self.service_account_email:
                found = True
        return found

    def get_subfolder_id(self, parent_id: str, folder_name: str) -> Optional[str]:
        query = (
            f"'{parent_id}' in parents and "
            f"name = '{folder_name}' and "
            f"mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        results = self.service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get("files", [])
        return files[0]["id"] if files else None

    def list_clients(self, active_clienti_folder_id: str) -> List[Tuple[str, str]]:
        query = (
            f"'{active_clienti_folder_id}' in parents and "
            f"mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        results = self.service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get("files", [])
        return [(f["name"], f["id"]) for f in files]
