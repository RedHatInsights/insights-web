import sys
import logging
from flask import json
from logstash_formatter import LogstashFormatterV1
from insights.settings import web as config

def initialize_logging():
    logger = logging.getLogger("")
    logger.setLevel(config["log_level"])
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        LogstashFormatterV1(fmt=json.dumps({"extra": {"component": "insights-plugins"}}))
    )
    logger.addHandler(handler)
    logging.getLogger("statsd").setLevel(logging.FATAL)
