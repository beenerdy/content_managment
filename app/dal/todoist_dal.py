import requests


class TodoistDAL:
    def __init__(self, token):
        self.token = token
        self.base_url = "https://api.todoist.com/rest/v2/"
        self._project_id_cache = {}
        self._user_id_cache = {}

    def get_project_id(self, project_name):
        # Cache lookup
        if project_name in self._project_id_cache:
            return self._project_id_cache[project_name]
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(self.base_url + "projects", headers=headers)
        resp.raise_for_status()
        for project in resp.json():
            if project["name"] == project_name:
                self._project_id_cache[project_name] = project["id"]
                return project["id"]
        raise ValueError(f"Project '{project_name}' not found in Todoist.")

    def get_user_id(self, email, project_id):
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.base_url}projects/{project_id}/collaborators"
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        for user in resp.json():
            if user.get("email") == email:
                return user["id"]
        raise ValueError(
            f"User with email '{email}' not found in project collaborators."
        )

    def create_task(
        self,
        content,
        due_string=None,
        project_name="BeNerdy Internal",
        assignee_email="e.cornitel@gmail.com",
    ):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        data = {"content": content}
        if due_string:
            data["due_string"] = due_string
        if project_name:
            project_id = self.get_project_id(project_name)
            data["project_id"] = project_id
        else:
            project_id = None
        if assignee_email and project_id:
            data["assignee_id"] = self.get_user_id(assignee_email, project_id)
        print(data)

        resp = requests.post(self.base_url + "tasks", json=data, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def task_exists(self, identifier):
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(self.base_url + "tasks", headers=headers)
        resp.raise_for_status()
        tasks = resp.json()
        return any(identifier in task["content"] for task in tasks)
