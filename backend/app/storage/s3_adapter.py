from __future__ import annotations

import io
from typing import Any
from urllib.parse import urlparse

import boto3
from botocore.client import BaseClient
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.core.exceptions import StorageError
from app.core.logging import get_logger
from app.storage.base import StorageBackend

logger = get_logger(__name__)

_LOCAL_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1"})


def _is_local_endpoint(endpoint_url: str | None) -> bool:
    """Return True only for explicit local-development endpoints.

    TLS certificate verification may be disabled solely for these endpoints
    (e.g. MinIO running on localhost). Production AWS S3 endpoints are never
    treated as local.
    """
    if not endpoint_url:
        return False
    hostname = urlparse(endpoint_url).hostname
    if hostname is None:
        return False
    hostname = hostname.lower()
    return hostname in _LOCAL_HOSTNAMES or hostname.endswith(".local") or "minio" in hostname


class S3StorageBackend(StorageBackend):
    def __init__(self) -> None:
        self._client: BaseClient | None = None
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        client_kwargs: dict[str, Any] = {
            "service_name": "s3",
            "aws_access_key_id": settings.S3_ACCESS_KEY_ID,
            "aws_secret_access_key": settings.S3_SECRET_ACCESS_KEY,
            "region_name": settings.S3_REGION,
            "config": BotoConfig(
                retries={"max_attempts": 3, "mode": "adaptive"},
                connect_timeout=10,
                read_timeout=30,
            ),
        }

        if settings.S3_ENDPOINT_URL:
            client_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL

        if not settings.S3_USE_SSL and _is_local_endpoint(settings.S3_ENDPOINT_URL):
            client_kwargs["verify"] = False
            logger.warning(
                "s3_tls_verification_disabled_for_local_endpoint",
                endpoint=settings.S3_ENDPOINT_URL,
            )

        try:
            self._client = boto3.client(**client_kwargs)
            self._initialized = True
            logger.info("s3_storage_initialized", endpoint=settings.S3_ENDPOINT_URL)
        except (BotoCoreError, ClientError) as e:
            logger.error("s3_storage_init_failed", error=str(e))
            raise StorageError(message="Failed to initialize S3 storage", details={"error": str(e)})

        # Provision the configured buckets. A fresh object store (MinIO on an
        # empty volume, which is how docker compose starts it) has neither
        # bucket, and every subsequent PutObject fails with NoSuchBucket.
        # Provisioning is best-effort: a store the app may not create is not a
        # startup failure, the first real upload still surfaces the error.
        for bucket_name in (settings.S3_BUCKET_NAME, settings.S3_PUBLIC_BUCKET_NAME):
            if not bucket_name:
                continue
            try:
                await self._ensure_bucket(bucket_name)
            except (BotoCoreError, ClientError, StorageError) as e:
                logger.warning("s3_bucket_provisioning_skipped", bucket=bucket_name, error=str(e))

    async def _ensure_bucket(self, bucket_name: str) -> None:
        if not self._client:
            raise StorageError("S3 client not initialized")
        try:
            self._client.head_bucket(Bucket=bucket_name)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "404":
                if settings.S3_ENDPOINT_URL:
                    self._client.create_bucket(Bucket=bucket_name)
                else:
                    self._client.create_bucket(
                        Bucket=bucket_name,
                        CreateBucketConfiguration={"LocationConstraint": settings.S3_REGION},
                    )
                logger.info("s3_bucket_created", bucket=bucket_name)

    async def upload_fileobj(
        self,
        file_obj: io.BytesIO,
        key: str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        if not self._client:
            raise StorageError("S3 client not initialized")

        bucket = settings.S3_BUCKET_NAME
        extra_args: dict[str, Any] = {}
        if content_type:
            extra_args["ContentType"] = content_type
        if metadata:
            extra_args["Metadata"] = metadata

        try:
            self._client.upload_fileobj(
                Fileobj=file_obj,
                Bucket=bucket,
                Key=key,
                ExtraArgs=extra_args or None,
            )
            logger.info("s3_upload_completed", bucket=bucket, key=key)
            return key
        except (BotoCoreError, ClientError) as e:
            logger.error("s3_upload_failed", bucket=bucket, key=key, error=str(e))
            raise StorageError(
                message="File upload failed",
                details={"bucket": bucket, "key": key, "error": str(e)},
            )

    async def download_fileobj(self, key: str) -> bytes:
        if not self._client:
            raise StorageError("S3 client not initialized")

        bucket = settings.S3_BUCKET_NAME
        try:
            response = self._client.get_object(Bucket=bucket, Key=key)
            data: bytes = response["Body"].read()
            return data
        except (BotoCoreError, ClientError) as e:
            logger.error("s3_download_failed", bucket=bucket, key=key, error=str(e))
            raise StorageError(
                message="File download failed",
                details={"bucket": bucket, "key": key, "error": str(e)},
            )

    async def delete_object(self, key: str) -> None:
        if not self._client:
            raise StorageError("S3 client not initialized")

        try:
            self._client.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
            logger.info("s3_delete_completed", key=key)
        except (BotoCoreError, ClientError) as e:
            logger.error("s3_delete_failed", key=key, error=str(e))
            raise StorageError(
                message="File deletion failed",
                details={"key": key, "error": str(e)},
            )

    async def object_exists(self, key: str) -> bool:
        if not self._client:
            raise StorageError("S3 client not initialized")

        try:
            self._client.head_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "404":
                return False
            raise

    async def list_objects(self, prefix: str = "") -> list[dict[str, Any]]:
        if not self._client:
            raise StorageError("S3 client not initialized")

        try:
            response = self._client.list_objects_v2(
                Bucket=settings.S3_BUCKET_NAME,
                Prefix=prefix,
            )
            return [
                {
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                    "etag": obj["ETag"].strip('"'),
                }
                for obj in response.get("Contents", [])
            ]
        except (BotoCoreError, ClientError) as e:
            logger.error("s3_list_failed", prefix=prefix, error=str(e))
            raise StorageError(
                message="Failed to list objects",
                details={"prefix": prefix, "error": str(e)},
            )

    async def generate_presigned_url(
        self,
        key: str,
        expiration: int = 3600,
        method: str = "get_object",
    ) -> str:
        if not self._client:
            raise StorageError("S3 client not initialized")

        try:
            url: str = self._client.generate_presigned_url(
                ClientMethod=method,
                Params={"Bucket": settings.S3_BUCKET_NAME, "Key": key},
                ExpiresIn=expiration,
            )
            return url
        except (BotoCoreError, ClientError) as e:
            logger.error("s3_presigned_url_failed", key=key, error=str(e))
            raise StorageError(
                message="Failed to generate presigned URL",
                details={"key": key, "error": str(e)},
            )

    async def list_buckets(self) -> list[dict[str, str]]:
        if not self._client:
            raise StorageError("S3 client not initialized")

        try:
            response = self._client.list_buckets()
            return [
                {"name": b["Name"], "creation_date": b["CreationDate"].isoformat()}
                for b in response.get("Buckets", [])
            ]
        except (BotoCoreError, ClientError) as e:
            logger.error("s3_list_buckets_failed", error=str(e))
            raise StorageError(message="Failed to list buckets", details={"error": str(e)})

    async def close(self) -> None:
        if self._client:
            self._client.close()
            self._initialized = False
            logger.info("s3_storage_closed")
