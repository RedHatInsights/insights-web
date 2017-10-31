import logging
import os
import datetime

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
    sd_bucket = os.environ.get("sd_s3_bucket")
    sd_whitelist = os.environ.get("sd_whitelist", "").split(",")
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


def s3_post(path, bucket_name, fname, system_id):
    try:
        with open(path, "rb") as fp:
            s3_client.upload_fileobj(fp, bucket_name, fname)
    except Exception as e:
        logger.warning("Error sending [%s] archive to s3 bucket %s: %s",
                       system_id, bucket_name, e.message)


def save(path, system_id, content_type, account_number):
    # ensure all env vars are properly set and this is an insights archive
    if s3_client and system_id:
        fname = ".".join([system_id, EXTENSIONS[content_type]])
        s3_post(path, bucket, fname, system_id)
        if account_number in sd_whitelist:
            sd_fname = "%s/%s/%s.%s" % (
                account_number,
                system_id,
                datetime.date.today(),
                EXTENSIONS[content_type]
            )
            s3_post(path, sd_bucket, sd_fname, system_id)
