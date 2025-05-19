from google.cloud import vision


class VisionService:
    def __init__(self, service_account_json):
        self.client = vision.ImageAnnotatorClient.from_service_account_file(
            service_account_json
        )

    def get_labels(self, image_content):
        image = vision.Image(content=image_content)
        response = self.client.label_detection(image=image)
        return [label.description for label in response.label_annotations]
