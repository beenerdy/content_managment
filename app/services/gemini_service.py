import requests


class GeminiService:
    def __init__(self, api_key):
        self.api_key = api_key
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.api_key}"

    def generate_caption(self, labels, prompt, hashtags, image_description=None):
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
        response = requests.post(self.url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
