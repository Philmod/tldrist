"""GCS storage client for uploading public images."""

import hashlib
from datetime import datetime

from google.cloud import storage

from tldrist.utils.logging import get_logger

logger = get_logger(__name__)


class ImageStorage:
    """Client for uploading images to a public GCS bucket."""

    def __init__(self, bucket_name: str) -> None:
        """Initialize the storage client.

        Args:
            bucket_name: Name of the GCS bucket to use.
        """
        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket_name)
        self._bucket_name = bucket_name

    def upload_image(self, image_data: bytes, mime_type: str, task_id: str) -> str:
        """Upload an image to GCS and return its public URL.

        Args:
            image_data: The image bytes.
            mime_type: The image MIME type (e.g., 'image/png').
            task_id: The Todoist task ID for organizing the image.

        Returns:
            The public URL of the uploaded image.
        """
        content_hash = hashlib.sha256(image_data).hexdigest()[:12]
        ext = "png" if "png" in mime_type else "jpeg"
        blob_name = f"figures/{datetime.now():%Y/%m}/{task_id}-{content_hash}.{ext}"

        blob = self._bucket.blob(blob_name)
        blob.upload_from_string(image_data, content_type=mime_type)

        logger.info(
            "Uploaded image to GCS",
            bucket=self._bucket_name,
            blob=blob_name,
            size=len(image_data),
        )

        return str(blob.public_url)
