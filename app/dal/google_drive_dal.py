import json
import os
import re
import time
from typing import List, Optional, Tuple

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload


class GoogleDriveDAL:
    SCOPES = ["https://www.googleapis.com/auth/drive"]
    IMAGES_DIR = "temp_images"

    def __init__(self, service_account_file: str):
        if not os.path.exists(self.IMAGES_DIR):
            os.makedirs(self.IMAGES_DIR)
        self.creds = service_account.Credentials.from_service_account_file(
            service_account_file, scopes=self.SCOPES
        )
        self.service = build("drive", "v3", credentials=self.creds)
        self.service_account_email = self._get_service_account_email(
            service_account_file
        )

    def list_images_in_folder(self, folder_id: str):
        response = (
            self.service.files()
            .list(
                q=f"'{folder_id}' in parents and mimeType contains 'image/'",
                fields="files(id, name, mimeType, webContentLink, thumbnailLink)",
            )
            .execute()
        )
        return response.get("files", [])

    def list_images_with_grouping(self, folder_id: str, retry_count=0, max_retries=5):
        """
        Recursively lists all images in the given folder, including images in subfolders
        with names matching the date-group pattern. Adds group info to each image.
        Handles rate limiting with exponential backoff.
        """
        import re

        date_group_pattern = re.compile(r"\d{2}\.\d{2}\.\d{2}-\d+")
        images = []

        try:
            response = (
                self.service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields="files(id, name, mimeType, webContentLink, thumbnailLink)",
                )
                .execute()
            )
        except HttpError as e:
            if e.resp.status == 429 and retry_count < max_retries:
                wait_time = 2**retry_count
                print(
                    f"Rate limit hit (429). Sleeping for {wait_time} seconds... (retry {retry_count+1}/{max_retries})"
                )
                time.sleep(wait_time)
                return self.list_images_with_grouping(
                    folder_id, retry_count=retry_count + 1, max_retries=max_retries
                )
            else:
                print(f"Google API error: {e}")
                raise

        files = response.get("files", [])

        for f in files:
            if f["mimeType"].startswith("image/"):
                images.append({**f, "group": None})
            elif f["mimeType"] == "application/vnd.google-apps.folder":
                if date_group_pattern.fullmatch(f["name"]):
                    try:
                        sub_response = (
                            self.service.files()
                            .list(
                                q=f"'{f['id']}' in parents and mimeType contains 'image/' and trashed = false",
                                fields="files(id, name, mimeType, webContentLink, thumbnailLink)",
                            )
                            .execute()
                        )
                        sub_images = sub_response.get("files", [])
                        for img in sub_images:
                            images.append({**img, "group": f["name"]})
                    except HttpError as e:
                        if e.resp.status == 429 and retry_count < max_retries:
                            wait_time = 2**retry_count
                            print(
                                f"Subfolder rate limit hit (429). Sleeping for {wait_time} seconds... (retry {retry_count+1}/{max_retries})"
                            )
                            time.sleep(wait_time)
                            # Retry this subfolder only
                            return self.list_images_with_grouping(
                                folder_id,
                                retry_count=retry_count + 1,
                                max_retries=max_retries,
                            )
                        else:
                            print(f"Google API error in subfolder: {e}")
                            raise
        return images

    def download_file(self, file_id: str, file_name: str = None) -> str:
        """
        Downloads a file from Google Drive to the local IMAGES_DIR, avoiding re-downloads.
        If file_name is not provided, it is fetched from Drive metadata.
        Returns the local filename, or None if download fails.
        """
        # If file_name is not given, get it from Drive API
        if file_name is None:
            try:
                file_metadata = (
                    self.service.files().get(fileId=file_id, fields="name").execute()
                )
                file_name = file_metadata["name"]
            except Exception as e:
                print(f"Failed to fetch metadata for file {file_id}: {e}")
                return None

        # Sanitize the filename
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", file_name)
        file_path = os.path.join(self.IMAGES_DIR, safe_name)

        # Check if file already exists
        if os.path.exists(file_path):
            print(f"File {safe_name} already exists, skipping download")
            return safe_name

        print(f"Downloading {safe_name}...")

        try:
            request = self.service.files().get_media(fileId=file_id)
            with open(file_path, "wb") as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        print(f"Download {int(status.progress() * 100)}%.")
            print(f"Downloaded {safe_name}")
            return safe_name
        except Exception as e:
            print(f"Failed to download file {file_id} as {safe_name}: {e}")
            return None

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

    def list_files_in_folder(
        self, folder_id: str, fields: str = "files(id, name, mimeType)"
    ):
        """Return a list of files in the given folder ID."""
        return (
            self.service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'",
                fields=fields,
            )
            .execute()
        ).get("files", [])

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
