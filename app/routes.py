import urllib3
from flask import jsonify, request, send_from_directory
from flask_cors import CORS

from dal.google_drive_dal import GoogleDriveDAL

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def register_routes(app):
    CORS(app, origins=["http://localhost:3000"])

    @app.route("/client/<client_uuid>/add_id", methods=["POST"])
    def add_id(client_uuid):
        data = request.json
        service = data.get("service")
        key = data.get("key")
        url = data.get("url")
        description = data.get("description")

        if not all([service, key, url, description]):
            return jsonify({"error": "Missing required fields"}), 400

        client = app.client_map.get_client(client_uuid)
        if not client:
            return jsonify({"error": f"Client UUID {client_uuid} not found."}), 404

        try:
            if service == "google_drive":
                id_value = app.drive_dal.extract_folder_id(url)
            elif service == "notion":
                print(app.notion_dal)
                id_value = app.notion_dal.extract_notion_id(url)
            else:
                return (
                    jsonify({"error": "Service must be 'google_drive' or 'notion'."}),
                    400,
                )
            client.add_resource(service, key, id_value, description, url)
            app.client_map.save_to_file(app.config["CLIENT_MAP_PATH"])
            return jsonify({"message": "ID added successfully"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/client/<client_uuid>/captions", methods=["GET"])
    def get_captions(client_uuid):
        message, error = app.client_manager.get_captions_for_client(client_uuid)
        if error:
            # Return error as plain text with 404
            return error, 404, {"Content-Type": "text/plain; charset=utf-8"}
        return message, 200, {"Content-Type": "text/plain; charset=utf-8"}

    @app.route("/client/<client_uuid>/images", methods=["GET"])
    def get_client_images(client_uuid):
        try:
            images = app.client_manager.get_images_for_client(client_uuid)
            return jsonify(images)
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404
        except Exception as e:
            print(f"Error in get_client_images: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/images/<filename>")
    def serve_image(filename):
        return send_from_directory(GoogleDriveDAL.IMAGES_DIR, filename)

    @app.route("/client/<client_uuid>/generate-captions", methods=["POST"])
    def generate_captions(client_uuid):
        try:
            app.client_manager.generate_captions_for_client(client_uuid)
            return jsonify({"message": "Caption generation completed"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/client_map", methods=["GET"])
    def get_client_map():
        return jsonify(app.client_map.to_dict())

    @app.route("/export", methods=["POST"])
    def export_images():
        try:
            data = request.json
            client_id = data.get("clientId")
            items = data.get("items", [])

            # Validate input
            if not client_id:
                return (
                    jsonify({"success": False, "message": "Client ID is required"}),
                    400,
                )

            client = app.client_map.get_client(client_id)
            if not client:
                return (
                    jsonify(
                        {"success": False, "message": f"Client not found: {client_id}"}
                    ),
                    404,
                )

            # Get the client's next_post_id folder
            next_post_id = client.get_google_drive_id("next_post_id")
            if not next_post_id:
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": f"next_post_id not configured for client {client.client_name}",
                        }
                    ),
                    400,
                )

            # Track results
            processed_count = 0
            errors = []

            # Process each item
            for item in items:
                position = item.get("position")
                is_carousel = item.get("isCarousel", False)
                images = item.get("images", [])

                for image in images:
                    try:
                        original_id = image.get("originalId", "")
                        export_prefix = (
                            image.get("exportFilename", "")
                            .replace(".jpg", "")
                            .replace(".jpeg", "")
                            .replace(".png", "")
                        )
                        original_filename = image.get("originalFilename", "")

                        if (
                            not original_id
                            or not export_prefix
                            or not original_filename
                        ):
                            errors.append(
                                f"Missing data for item at position {position}"
                            )
                            continue

                        # Format the new filename with the prefix
                        new_filename = f"{export_prefix}-{original_filename}"

                        # Create file metadata for the copy
                        file_metadata = {
                            "name": new_filename,
                            "parents": [next_post_id],
                        }

                        # Copy the file to the next_post_id folder with the new name
                        copied_file = (
                            app.drive_dal.service.files()
                            .copy(
                                fileId=original_id,
                                body=file_metadata,
                                fields="id, name",
                            )
                            .execute()
                        )

                        if copied_file and copied_file.get("id"):
                            processed_count += 1
                            app.logger.info(
                                f"Exported {new_filename} to {client.client_name}'s next_post_id folder"
                            )
                        else:
                            errors.append(f"Failed to copy file for {new_filename}")

                    except HttpError as e:
                        error_msg = (
                            f"Google API error for position {position}: {str(e)}"
                        )
                        app.logger.error(error_msg)
                        errors.append(error_msg)
                    except Exception as e:
                        error_msg = (
                            f"Error processing image at position {position}: {str(e)}"
                        )
                        app.logger.error(error_msg)
                        errors.append(error_msg)

            # Generate response
            if errors:
                return jsonify(
                    {
                        "success": True,
                        "message": f"Exported {processed_count} images with {len(errors)} errors",
                        "errors": errors,
                    }
                )
            else:
                return jsonify(
                    {
                        "success": True,
                        "message": f"Successfully exported {processed_count} images to {client.client_name}'s next posts folder",
                    }
                )

        except Exception as e:
            app.logger.error(f"Export error: {str(e)}")
            return (
                jsonify({"success": False, "message": f"Export failed: {str(e)}"}),
                500,
            )

    @app.route("/client", methods=["POST"])
    def create_client_from_notion():
        data = request.json
        try:
            client = app.client_manager.create_client_from_payload(data)
            return (
                jsonify(
                    {
                        "uuid": client.uuid,
                        "message": "Client created",
                        "client": client.to_dict(),
                    }
                ),
                201,
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/buffer-check", methods=["POST"])
    def buffer_check():
        try:
            app.client_manager.ensure_content_buffer(app.todoist_dal)
            return jsonify({"message": "Buffer check completed"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/sync-next-posts/<client_uuid>", methods=["POST"])
    def sync_client_next_posts(client_uuid):
        try:
            app.client_manager.sync_next_posts_from_drive_to_notion(client_uuid)
            return jsonify({"message": "Sync triggered"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 400
