from flask import jsonify, request


def register_routes(app):
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

    @app.route("/client_map", methods=["GET"])
    def get_client_map():
        return jsonify(app.client_map.to_dict())

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
