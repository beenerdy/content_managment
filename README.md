# Drive Client Automation

Automate mapping, watching, and processing of Google Drive folders for each client, and integrate with Notion for content workflows.

---

## 🚀 Project Structure

```plaintext
drive-client-automation/
│
├── README.md
├── requirements.txt
├── service-account.json           # (DO NOT COMMIT TO GIT)
│
├── folder_mapping.py              # Step 1: Build client-to-next-post-folder map
├── watcher_setup.py               # Step 2: Set up Google Drive watchers/webhooks
├── webhook_handler.py             # Cloud Function handler for Drive notifications
├── notion_integration.py          # Functions for pushing data to Notion
├── utils.py                       # Shared helper functions
│
├── client_next_post_map.json      # Output of mapping step
├── channel_map.json               # Output of watcher setup step
│
└── .gitignore
```

---

## 🛠️ Setup

### 1. Clone the repository and create a virtual environment

```bash
git clone <your-repo-url>
cd drive-client-automation
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Create and configure a Google Cloud Service Account

-  In your [Google Cloud Console](https://console.cloud.google.com/):
  - Select or create your project.
  - Go to **IAM & Admin > Service Accounts**.
  - Create a new Service Account (e.g., `drive-folder-mapper`).
  - Grant it at least the **Editor** or **Drive Admin** role.
  - Create and download a JSON key. Place it in the project root as `service-account.json`.

### 4. Share your Google Drive folders

-  In Google Drive, share the relevant top-level folder (e.g., `BeeNerdy`) with the service account email.

### 5. Enable Google Drive API

-  In your Google Cloud project, go to **APIs & Services > Library** and enable the **Google Drive API**.

---

## 🗂️ Workflow

### **Step 1: Build the Client-to-Next-Post-Folder Map**

```bash
python folder_mapping.py
```

-  Outputs `client_next_post_map.json` mapping each client to their `0. Next Post` folder ID.

### **Step 2: Set Up Google Drive Watchers (Webhooks)**

```bash
python watcher_setup.py
```

-  Registers a webhook for each folder, outputs `channel_map.json`.

### **Step 3: Deploy Webhook Handler**

-  Deploy `webhook_handler.py` as a Google Cloud Function.
-  After deployment, use the function’s HTTPS URL as your webhook endpoint in watcher setup.

### **Step 4: Notion Integration**

-  Configure your Notion integration and secret.
-  Share your Notion database with the integration.
-  Use `notion_integration.py` in your webhook handler to push data to Notion.

---

## 🔒 Security

-  **Never commit `service-account.json`, `client_next_post_map.json`, or `channel_map.json` to git.**
-  Use `.gitignore` to exclude secrets and cache files.

---

## 📝 .gitignore Example

```
service-account.json
client_next_post_map.json
channel_map.json
__pycache__/
*.pyc
venv/
```

---

## 📚 References

-  [Google Drive API Python Quickstart](https://developers.google.com/drive/api/v3/quickstart/python)
-  [Google Cloud Functions](https://cloud.google.com/functions/docs)
-  [Notion API Python Client](https://github.com/ramnes/notion-sdk-py)

---

## 🤝 Contributing

Feel free to open issues or submit PRs to improve the workflow!
