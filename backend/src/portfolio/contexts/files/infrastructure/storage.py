"""S3-compatible object storage (MinIO on the VPS). boto3 is synchronous, so every
call runs in a thread to keep the event loop free."""

import asyncio
import json
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client


def create_s3_client(endpoint_url: str, access_key: str, secret_key: str, region: str) -> S3Client:
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        # MinIO serves buckets as paths (host/bucket/key), not subdomains.
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
    )


def content_disposition(filename: str) -> str:
    """RFC 6266: an ASCII fallback plus the UTF-8 name for browsers that support it."""
    ascii_name = filename.encode("ascii", "replace").decode().replace('"', "").replace("?", "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def public_read_policy(bucket: str) -> str:
    """Anyone may GET an object by its exact key; nobody may list the bucket."""
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/*"],
                }
            ],
        }
    )


class S3Storage:
    def __init__(self, client: S3Client, bucket: str, public_base_url: str) -> None:
        self._client = client
        self._bucket = bucket
        self._public_base_url = public_base_url

    async def put(self, key: str, data: bytes, content_type: str, filename: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            ContentDisposition=content_disposition(filename),
            # Keys never change content, so browsers and CDNs may cache them forever.
            CacheControl="public, max-age=31536000, immutable",
        )

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)

    def public_url(self, key: str) -> str:
        return f"{self._public_base_url}/{key}"

    async def ensure_bucket(self) -> None:
        """Create the bucket if needed and apply the read-only public policy."""
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self._bucket)
        except ClientError:
            await asyncio.to_thread(self._client.create_bucket, Bucket=self._bucket)
        await asyncio.to_thread(
            self._client.put_bucket_policy,
            Bucket=self._bucket,
            Policy=public_read_policy(self._bucket),
        )
