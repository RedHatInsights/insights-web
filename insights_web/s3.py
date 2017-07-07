import boto3
import os

if all(lambda k: k in os.environ, ["s3_bucket", "aws_access_key_id", "aws_secret_access_key"]):
    bucket = os.environ["s3_bucket"]
    access_key_id = os.environ["aws_access_key_id"]
    secret_access_key = os.environ["aws_secret_access_key"]
    s3_client = boto3.client('s3')
else:
    bucket = access_key_id = secret_access_key = s3_client = None


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
