"""Thin wrapper around the MinIO Python SDK for evidence object storage."""

import io
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from app.config import settings


import os

class MinIOClient:
    """MinIO object storage client with automatic local filesystem fallback."""

    def __init__(self) -> None:
        self.local_mode = False
        self.endpoint = settings.MINIO_ENDPOINT
        self.bucket = settings.MINIO_BUCKET

        if not self.endpoint or self.endpoint.lower() in ("", "local", "none", "false"):
            self.local_mode = True
        else:
            try:
                self.client = Minio(
                    endpoint=settings.MINIO_ENDPOINT,
                    access_key=settings.MINIO_ACCESS_KEY,
                    secret_key=settings.MINIO_SECRET_KEY,
                    secure=settings.MINIO_SECURE,
                )
                # Test connectivity
                self.client.list_buckets()
            except Exception:
                self.local_mode = True

        if self.local_mode:
            self.local_dir = os.path.join(os.getcwd(), "data", "evidence")
            os.makedirs(self.local_dir, exist_ok=True)

    def ensure_bucket(self) -> None:
        """Create the evidence bucket if it does not exist or ensure local storage directory exists."""
        if self.local_mode:
            os.makedirs(self.local_dir, exist_ok=True)
        else:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)

    def upload_bytes(self, object_key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload raw bytes to MinIO or local filesystem. Returns the object key."""
        if self.local_mode:
            # Replace slashes with underscores to flat-store inside local directory safely
            safe_key = object_key.replace("/", "_")
            file_path = os.path.join(self.local_dir, safe_key)
            with open(file_path, "wb") as f:
                f.write(data)
            return object_key
        else:
            self.client.put_object(
                bucket_name=self.bucket,
                object_name=object_key,
                data=io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            return object_key

    def download_bytes(self, object_key: str) -> bytes:
        """Download an object's content as bytes from MinIO or local filesystem."""
        if self.local_mode:
            safe_key = object_key.replace("/", "_")
            file_path = os.path.join(self.local_dir, safe_key)
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Local evidence file not found: {file_path}")
            with open(file_path, "rb") as f:
                return f.read()
        else:
            response = self.client.get_object(self.bucket, object_key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

    def get_presigned_url(self, object_key: str, expires: timedelta = timedelta(hours=1)) -> str:
        """Generate a presigned URL or direct local download URL pointing to backend API."""
        if self.local_mode:
            # object_key is in the format case_id/artifact_id
            parts = object_key.split("/")
            artifact_id = parts[1] if len(parts) == 2 else object_key
            backend_url = getattr(settings, "BACKEND_URL", "http://localhost:8000").rstrip("/")
            return f"{backend_url}/evidence/{artifact_id}/download"
        else:
            return self.client.presigned_get_object(
                bucket_name=self.bucket,
                object_name=object_key,
                expires=expires,
            )

    def health_check(self) -> bool:
        """Check connectivity to MinIO or verify local filesystem workspace accessibility."""
        if self.local_mode:
            return os.path.exists(self.local_dir) and os.access(self.local_dir, os.W_OK)
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
