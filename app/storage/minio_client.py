"""Thin wrapper around the MinIO Python SDK for evidence object storage."""

import io
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from app.config import settings


class MinIOClient:
    """MinIO object storage client for evidence artifacts."""

    def __init__(self) -> None:
        self.client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self.bucket = settings.MINIO_BUCKET

    def ensure_bucket(self) -> None:
        """Create the evidence bucket if it does not exist."""
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def upload_bytes(self, object_key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload raw bytes to MinIO. Returns the object key."""
        self.client.put_object(
            bucket_name=self.bucket,
            object_name=object_key,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return object_key

    def download_bytes(self, object_key: str) -> bytes:
        """Download an object's content as bytes."""
        response = self.client.get_object(self.bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def get_presigned_url(self, object_key: str, expires: timedelta = timedelta(hours=1)) -> str:
        """Generate a presigned URL for downloading an object."""
        return self.client.presigned_get_object(
            bucket_name=self.bucket,
            object_name=object_key,
            expires=expires,
        )

    def health_check(self) -> bool:
        """Check connectivity to MinIO by listing buckets."""
        try:
            self.client.list_buckets()
            return True
        except Exception:
            return False


# Module-level singleton, initialized on first import in main.py lifespan
minio_client: MinIOClient | None = None


def get_minio_client() -> MinIOClient:
    """Return the initialized MinIO client singleton."""
    global minio_client
    if minio_client is None:
        minio_client = MinIOClient()
        minio_client.ensure_bucket()
    return minio_client
