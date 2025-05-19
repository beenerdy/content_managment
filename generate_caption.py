import json
import logging
import os
import sys
import traceback

import requests
from flask import Flask, request
from google.cloud import vision
from google.oauth2 import service_account
from googleapiclient.discovery import build
from notion_client import Client as NotionClient

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Environment variables
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SERVICE_ACCOUNT_FILE = "service-account.json"

# Initialize Notion client
if not NOTION_TOKEN:
    logging.error("NOTION_TOKEN environment variable not set.")
    notion = None
else:
    notion = NotionClient(auth=NOTION_TOKEN)
    logging.info("Notion client initialised.")


def get_drive_service():
    """Build and return the Google Drive service using the service account."""
    logging.debug("Building Google Drive service.")
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)


def download_image(file_id):
    """Download the image from Google Drive using the file ID."""
    logging.info(f"Downloading image from Google Drive with file_id: {file_id}")
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id)
    file_content = request.execute()
    logging.debug(f"Downloaded image content of size: {len(file_content)} bytes")
    return file_content


def analyze_image(image_content):
    """Analyze the image using Google Cloud Vision API and return labels."""
    logging.info("Analyzing image with Google Cloud Vision API.")
    client = vision.ImageAnnotatorClient.from_service_account_file(SERVICE_ACCOUNT_FILE)
    image = vision.Image(content=image_content)
    response = client.label_detection(image=image)
    labels = [label.description for label in response.label_annotations]
    logging.info(f"Image analysis labels: {labels}")
    return labels


def generate_caption(labels, prompt, hashtags, image_description=None):
    """Generate a caption using the Gemini API."""
    logging.info("Generating caption using Gemini API.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

    image_desc_part = ""
    if image_description:
        image_desc_part = f" The image is described as: '{image_description.strip()}'. Give this description high importance in the caption."

    input_text = (
        f"Generate a social media caption based on the following prompt: '{prompt.strip()}'."
        f"{image_desc_part} The image has these labels: {', '.join(labels)}."
        f" Include these hashtags: {', '.join(hashtags)}."
        f" Keep the caption under 50 words."
    )
    payload = {"contents": [{"parts": [{"text": input_text}]}]}
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        caption = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        logging.info(f"Generated caption: {caption}")
        return caption
    except Exception as e:
        logging.error(f"Failed to generate caption: {e}")
        raise


def get_notion_page(page_id):
    """Retrieve the Notion page properties."""
    logging.info(f"Retrieving Notion page with page_id: {page_id}")
    return notion.pages.retrieve(page_id)


def get_smm_page(smm_page_id):
    """Retrieve the Social Media Management page details."""
    logging.info(f"Retrieving SMM page with id: {smm_page_id}")
    smm_page = notion.pages.retrieve(smm_page_id)
    hashtags_prop = smm_page["properties"]["Hashtags"]["rich_text"]
    if hashtags_prop:
        hashtags_text = "".join([t["plain_text"] for t in hashtags_prop])
        hashtags = [h.strip() for h in hashtags_text.split() if h.strip()]
    else:
        hashtags = []
    logging.info(f"Extracted hashtags: {hashtags}")
    blocks = notion.blocks.children.list(block_id=smm_page_id)
    prompt = ""
    for block in blocks["results"]:
        if block["type"] == "paragraph" and block["paragraph"]["rich_text"]:
            prompt += block["paragraph"]["rich_text"][0]["text"]["content"] + "\n"
    logging.info(f"Extracted prompt: {prompt.strip()}")
    return prompt, hashtags


def generate_caption_handler(request):
    """Handle webhook requests triggered via Postman."""
    try:
        data = request.get_json()
        logging.info(f"Webhook payload: {data}")
        if not data or "page_id" not in data:
            logging.error("Invalid webhook payload. Expected 'page_id'.")
            return ("", 400)

        page_id = data["page_id"]
        page = get_notion_page(page_id)
        properties = page["properties"]

        # Extract Image Description
        image_description = ""
        try:
            image_desc_prop = properties.get("Image Description", {}).get(
                "rich_text", []
            )
            if image_desc_prop:
                image_description = "".join([t["plain_text"] for t in image_desc_prop])
            logging.info(f"Image Description: {image_description}")
        except Exception as e:
            logging.warning(f"Could not extract image description: {e}")

        # Check status
        status = properties["Status"]["status"]["name"]
        logging.info(f"Page {page_id} status: {status}")
        if status != "Suggest Captions":
            logging.info(
                f"Skipping page {page_id}: Status is '{status}', not 'Suggest Captions'."
            )
            return ("Status not 'Suggest Captions'", 200)

        # Extract Google Drive file ID
        drive_url = properties["Google Drive File"]["url"]
        try:
            file_id = drive_url.split("/d/")[1].split("/")[0]
            logging.info(f"Extracted file_id: {file_id} from URL: {drive_url}")
        except Exception:
            logging.error(
                f"Could not extract file_id from Google Drive URL: {drive_url}"
            )
            return ("", 400)

        # Get prompt and hashtags from Social Media Management page
        smm_relation = properties["Social Media Management"]["relation"]
        if not smm_relation:
            logging.error(f"No Social Media Management relation for page {page_id}.")
            return ("", 400)
        smm_page_id = smm_relation[0]["id"]
        prompt, hashtags = get_smm_page(smm_page_id)

        # Process image and generate caption
        image_content = download_image(file_id)
        labels = analyze_image(image_content)
        caption = generate_caption(
            labels, prompt, hashtags, image_description=image_description
        )

        # Update Notion page with caption
        logging.info(f"Appending caption to Notion page {page_id}")
        notion.blocks.children.append(
            block_id=page_id,
            children=[
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": caption}}]
                    },
                }
            ],
        )

        # Update status
        logging.info(
            f"Updating status for Notion page {page_id} to 'Caption Generated'"
        )
        notion.pages.update(
            page_id=page_id,
            properties={"Status": {"status": {"name": "Caption Generated"}}},
        )

        logging.info(f"Processed page {page_id}: Added caption and updated status.")
        return ("Caption generated and page updated", 200)

    except Exception as e:
        logging.error(f"Exception in generate_caption_handler: {e}", exc_info=True)
        return ("", 500)
