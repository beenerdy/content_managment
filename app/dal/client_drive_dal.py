import os
import re
import time


class ClientDriveDAL:
    def __init__(self, client, drive_dal):
        self.client = client
        self.drive_dal = drive_dal

    def get_ready_images(self):
        """
        Fetches all images from the client's fotos_id folder and
        returns a list of image metadata dicts with direct Google Drive URLs
        and a localUrl for Flask static serving.
        Downloads images locally for frontend consumption.
        Only returns after all images are downloaded or skipped if failed.
        Images are grouped if in subfolders with a group name.
        """
        fotos_id = self.client.get_google_drive_id("fotos_id")
        if not fotos_id:
            print("Fotos folder ID not found.")
            raise ValueError("Fotos folder ID not found for this client.")

        print(f"Listing images in folder ID: {fotos_id}")
        files = self.drive_dal.list_images_with_grouping(fotos_id)
        print(f"Found {len(files)} images.")

        images = []
        for file in files:
            if not file.get("mimeType", "").startswith("image/"):
                print(
                    f"Skipping non-image file: {file.get('name', 'N/A')} ({file.get('mimeType', 'N/A')})"
                )
                continue  # Skip if it's not an image

            # Download the image locally (synchronously)
            local_filename = self.drive_dal.download_file(file["id"], file["name"])
            if not local_filename:
                print(f"Skipping {file['name']} as download failed.")
                continue  # Skip if download failed

            # Construct the local URL for frontend
            local_url = f"/images/{local_filename}"

            images.append(
                {
                    "id": file["id"],
                    "name": file["name"],
                    "group": file.get("group"),
                    "url": f"https://lh3.googleusercontent.com/d/{file['id']}",
                    "driveUrl": f"https://lh3.googleusercontent.com/d/{file['id']}",
                    "alternativeUrl": f"https://drive.google.com/uc?export=view&id={file['id']}",
                    "thumbnailUrl": file.get("thumbnailLink"),
                    "mimeType": file.get("mimeType"),
                    "localUrl": local_url,  # <-- Added for frontend consumption
                }
            )
        print(f"Prepared {len(images)} image entries with Drive and local URLs.")
        images.sort(key=lambda x: (x["group"] or "", x["name"]))

        # Only returns after all downloads are done (which is already the case)
        return images

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
