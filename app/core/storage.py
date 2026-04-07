import uuid
import os
from abc import ABC, abstractmethod

import aiofiles


class StorageBackend(ABC):
    @abstractmethod
    async def store(self, content: bytes, filename: str, content_type: str) -> str:
        ...

    @abstractmethod
    async def retrieve(self, key: str) -> bytes:
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        ...


class LocalStorage(StorageBackend):
    def __init__(self, base_path: str):
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)

    async def store(self, content: bytes, filename: str, content_type: str) -> str:
        key = f"{uuid.uuid4()}_{filename}"
        path = os.path.join(self.base_path, key)
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)
        return key

    async def retrieve(self, key: str) -> bytes:
        path = os.path.join(self.base_path, key)
        async with aiofiles.open(path, "rb") as f:
            return await f.read()

    async def delete(self, key: str) -> None:
        path = os.path.join(self.base_path, key)
        if os.path.exists(path):
            os.remove(path)


class S3Storage(StorageBackend):
    def __init__(self, bucket: str, region: str, access_key: str, secret_key: str):
        import boto3
        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    async def store(self, content: bytes, filename: str, content_type: str) -> str:
        key = f"{uuid.uuid4()}_{filename}"
        self._client.put_object(Bucket=self.bucket, Key=key, Body=content, ContentType=content_type)
        return key

    async def retrieve(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    async def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)


_storage_instance: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _storage_instance
    if _storage_instance is None:
        from app.core.config import settings
        if settings.STORAGE_BACKEND == "s3":
            _storage_instance = S3Storage(
                bucket=settings.S3_BUCKET_NAME,
                region=settings.S3_REGION,
                access_key=settings.S3_ACCESS_KEY_ID,
                secret_key=settings.S3_SECRET_ACCESS_KEY,
            )
        else:
            _storage_instance = LocalStorage(settings.STORAGE_LOCAL_PATH)
    return _storage_instance
