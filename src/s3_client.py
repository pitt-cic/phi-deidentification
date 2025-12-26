import boto3
from pathlib import Path
import fnmatch

from .config import AWSConfig, DEFAULT_AWS_CONFIG

class S3Client:
    """Client for interacting with Amazon S3 buckets"""

    def __init__(self, config: AWSConfig | None = None):
        self.config = config or DEFAULT_AWS_CONFIG
        self._client = None

    @property
    def client(self):
        """Lazy initialization of boto3 client"""
        if self._client is None:
            self._client = boto3.client("s3", region_name=self.config.region)
        return self._client

    def list_objects(
            self,
            bucket: str,
            prefix: str,
            pattern: str | None = None,
            exclude_objects: list[str] | None = None,
            limit: int | None = None
    ):
        objects = []
        paginator = self.client.get_paginator("list_objects_v2")

        try:
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                if "Contents" not in page:
                    continue

                for obj in page["Contents"]:
                    key = obj["Key"]

                    if pattern and not fnmatch.fnmatch(key, pattern):
                        continue

                    filename = key.split("/")[-1]
                    if filename in exclude_objects:
                        continue

                    objects.append({"bucket": bucket, "key": key, "filename": filename})

                    # Check limit
                    if limit and len(objects) >= limit:
                        return objects
        except Exception as e:
            print(f"Error listing S3 objects: {e}")
            return []

        return objects

    def download_file(self, bucket: str, key: str, temp_dir: Path) -> Path:
        """
        Download a file from S3.

        Args:
            bucket: S3 bucket name
            key: S3 object key
            temp_dir: Local directory to download the file to

        Returns:
            The local path the file was downloaded to

        Raises:
             RuntimeError: If there was an error in downloading the file
        """
        try:
            filename = key.split('/')[-1]
            local_path = temp_dir / filename
            self.client.download_file(bucket, key, str(local_path))
            return local_path
        except Exception as e:
            raise RuntimeError(f"Failed to download s3://{bucket}/{key}: {e}")

    def upload(self, bucket: str, key: str, file: Path):
        """Upload a file to S3."""
        try:
            self.client.upload_file(str(file), bucket, key)
            print(f"Uploaded to s3://{bucket}/{key}")
        except Exception as e:
            print(f"Warning: Failed to upload to S3: {e}")

