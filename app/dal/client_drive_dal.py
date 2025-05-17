import os
import re


class ClientDriveDAL:
    def __init__(self, client, drive_dal):
        self.client = client
        self.drive_dal = drive_dal

    def count_ready_files(self, content_type):
        """
        Count files in the correct subfolder for this client and content type,
        filtering by appropriate mime types and file extensions.
        content_type: one of 'photos', 'short_videos', 'long_videos'
        """
        key_map = {
            "photos": "photos_id",
            "short_videos": "short_videos_id",
            "long_videos": "long_videos_id",
        }
        filter_map = {
            "photos": {
                "allowed_mime_types": ["image/"],
                "allowed_extensions": [".jpg", ".jpeg", ".png"],
            },
            "short_videos": {
                "allowed_mime_types": ["video/"],
                "allowed_extensions": [".mp4", ".mov"],
            },
            "long_videos": {
                "allowed_mime_types": ["video/"],
                "allowed_extensions": [".mp4", ".mov"],
            },
        }

        folder_key = key_map.get(content_type)
        filters = filter_map.get(content_type)
        if not folder_key or not filters:
            raise ValueError(f"Unknown content_type: {content_type}")

        subfolder_id = self.client.get_google_drive_id(folder_key)
        print(subfolder_id)
        if not subfolder_id:
            print(
                f"Subfolder ID for '{content_type}' not set for client {self.client.client_name}"
            )
            return 0

        try:
            files = self.drive_dal.list_files_in_folder(subfolder_id)
        except Exception as e:
            print(f"Error fetching files from Drive: {e}")
            return 0

        # Filter by MIME type
        allowed_mime_types = filters["allowed_mime_types"]
        files = [
            f
            for f in files
            if any(f["mimeType"].startswith(mt) for mt in allowed_mime_types)
        ]

        # Filter by extension
        allowed_extensions = filters["allowed_extensions"]
        files = [
            f
            for f in files
            if any(f["name"].lower().endswith(ext) for ext in allowed_extensions)
        ]

        return len(files)

    @staticmethod
    def parse_file_name(file_name):
        # Matches: prefix (digits + optional letter), dash, optional middle, base name, extension
        # Examples:
        # 1-25.03.30-7-COF08256.jpg => 1, 1, '', 25.03.30-7-COF08256
        # 2b-COF08256.jpg           => 2b, 2, 'b', COF08256
        # 3-MyFile.jpeg             => 3, 3, '', MyFile
        # 4-.jpg                    => 4, 4, '', ''
        m = re.match(r"^(\d+[a-zA-Z]?)-(.*)\.([^.]+)$", file_name)
        if m:
            group_key = m.group(1)
            num_letter_match = re.match(r"^(\d+)([a-zA-Z]?)$", group_key)
            num = num_letter_match.group(1)
            letter = num_letter_match.group(2)
            match_key = m.group(2)  # Can be empty string
            return group_key, num, letter, match_key
        return None, None, None, None

    def move_matching_files(self, match_key):
        fotos_id = self.client.get_google_drive_id("fotos_id")
        scheduling_id = self.client.get_google_drive_id("scheduling_id")
        try:
            fotos_files = self.drive_dal.list_files_in_folder(
                fotos_id, fields="files(id, name, parents)"
            )
            found = False
            for file in fotos_files:
                base_name, _ = os.path.splitext(file["name"])
                if base_name == match_key:
                    self.drive_dal.service.files().update(
                        fileId=file["id"],
                        addParents=scheduling_id,
                        removeParents=fotos_id,
                        fields="id, parents",
                    ).execute()
                    print(
                        f"Moved file '{file['name']}' from fotos_id to scheduling_id."
                    )
                    found = True
            if not found:
                print(f"File with base name '{match_key}' not found in fotos_id.")
        except Exception as e:
            print(f"ERROR moving file with base name '{match_key}': {e}")

    def list_next_posts(self):
        next_post_id = self.client.get_google_drive_id("next_post_id")
        return self.drive_dal.list_files_in_folder(
            next_post_id, fields="files(id, name, createdTime, parents)"
        )

    def make_file_public(self, file_id):
        try:
            self.drive_dal.service.permissions().create(
                fileId=file_id, body={"role": "reader", "type": "anyone"}, fields="id"
            ).execute()
            print(f"Made file {file_id} public.")
        except Exception as e:
            print(f"Could not make file public: {e}")
