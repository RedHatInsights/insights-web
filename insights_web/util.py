import sys
import logging
import traceback
from flask import json
from logstash_formatter import LogstashFormatterV1
from insights.settings import web as config

import threading
thread_context = threading.local()


class OurFormatter(LogstashFormatterV1):

    def format(self, record):
        if hasattr(thread_context, "request_id"):
            setattr(record, "request_id", thread_context.request_id)

        exc = getattr(record, "exc_info")
        if exc:
            setattr(record, "exception", "".join(traceback.format_exception(*exc)))
            setattr(record, "exc_info", None)

        return super(OurFormatter, self).format(record)


def initialize_logging():
    logger = logging.getLogger("")
    logger.setLevel(config["log_level"])
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        OurFormatter(fmt=json.dumps({"extra": {"component": "insights-plugins"}}))
    )
    logger.addHandler(handler)
    logging.getLogger("statsd").setLevel(logging.FATAL)
