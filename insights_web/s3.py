import logging
import os

logger = logging.getLogger(__name__)

if all(k in os.environ for k in ["s3_bucket", "aws_access_key_id", "aws_secret_access_key"]):
    import boto3
    bucket = os.environ["s3_bucket"]
    s3_client = boto3.client(
        's3',
        aws_access_key_id=os.environ["aws_access_key_id"],
        aws_secret_access_key=os.environ["aws_secret_access_key"]
    )
    logger.info("Successfully configured for s3 archive storage into bucket: %s", bucket)
else:
    logger.info("s3 storage not configured")
    bucket = s3_client = None


EXTENSIONS = {
    "application/x-xz": "tar.gz",
    "application/x-gzip": "tar.gz",
    "application/gzip": "tar.gz",
    "application/x-bzip2": "tar.bz",
    "application/x-tar": "tar"
}


def save(path, system_id, content_type):
    # ensure all env vars are properly set and this is an insights archive
    if s3_client and system_id:
        fname = ".".join([system_id, EXTENSIONS[content_type]])
        with open(path, "rb") as fp:
            s3_client.upload_fileobj(fp, bucket, fname)
