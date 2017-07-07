import logging
import time
import platform
import insights
import uuid
import tempfile
import os
import shutil
import sys
from flask import Flask, json, request, jsonify
from collections import defaultdict
from logstash_formatter import LogstashFormatterV1
from insights_web import s3
from insights.settings import web as config
from insights.core import plugins
from insights.core import archives, specs
from insights.core.evaluators import InsightsEvaluator, SingleEvaluator, InsightsMultiEvaluator

stats = defaultdict(int)
stats["start_time"] = time.time()

app = Flask(__name__)

MAX_UPLOAD_SIZE = 1024 * 1024 * 100

logger = logging.getLogger(__name__)


def format_seconds(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return "%02d:%02d:%02d" % (h, m, s)


def initialize_logging():
    logger = logging.getLogger("")
    logger.setLevel(config["log_level"])
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        LogstashFormatterV1(fmt=json.dumps({"extra": {"component": "insights-plugins"}}))
    )
    logger.addHandler(handler)
    logging.getLogger("statsd").setLevel(logging.FATAL)


class EngineError(Exception):
    def __init__(self, message, status_code=500):
        super(EngineError, self).__init__(message)
        self.status_code = status_code


def verify_file_size(file_size):
    if file_size > MAX_UPLOAD_SIZE:
        error_msg = "Upload is too big. %s/%s bytes" % (file_size, MAX_UPLOAD_SIZE)
        raise EngineError(error_msg, 413)
    if file_size == 0:
        raise EngineError("Upload has an empty archive body.", 400)


def extract():
    if "file" not in request.files:
        raise EngineError("No 'file' key found in form part", 400)
    file_loc = os.path.join(tempfile.mkdtemp(), "tmp.tar.gz")
    request.files["file"].save(file_loc)
    file_size = os.stat(file_loc).st_size
    verify_file_size(file_size)
    extractor = archives.TarExtractor().from_path(file_loc)
    return extractor, file_size, file_loc


def handle(extractor, system_id=None, account=None, config=None):
    spec_mapper = specs.SpecMapper(extractor)

    md_str = spec_mapper.get_content("metadata.json", split=False, default="{}")
    md = json.loads(md_str)

    if md and 'systems' in md:
        runner = InsightsMultiEvaluator(spec_mapper, system_id, md)
    elif spec_mapper.get_content("machine-id"):
        runner = InsightsEvaluator(spec_mapper, system_id=system_id)
    else:
        runner = SingleEvaluator(spec_mapper)
    return runner.process()


def handle_results(results, file_size, user_agent):
    upload_metadata = {
        "size": file_size,
        "client": user_agent,
        "uuid": uuid.uuid4().hex
    }
    if not results:
        raise EngineError("Rule results missing")
    elif isinstance(results, basestring):
        # String result means archive was invalid
        raise EngineError(results, 400)
    results["upload"] = upload_metadata
    return json.dumps(results) + "\r\n", 201, {"X-Engine-Host": platform.node()}


def update_stats(results, user_agent):
    if "clients" not in stats:
        stats["clients"] = defaultdict(int)
    stats["clients"][user_agent] += 1
    stats["archives_processed"] += 1
    stats["rules_returned"] += len(results["reports"])
    stats["bytes_processed"] += results["upload"]["size"]


@app.errorhandler(EngineError)
def handle_error(error):
    return error.message, error.status_code, None


@app.route("/status")
def status():
    if "versions" not in stats:
        versions = stats["versions"] = {}
        versions["insights-core"] = {"version": insights.get_nvr(),
                                     "commit": insights.package_info["COMMIT"]}
        versions.update(insights.RULES_STATUS)
    stats["uptime"] = format_seconds(time.time() - stats["start_time"])
    return jsonify(stats)


@app.route("/upload/<system_id>", methods=["POST"])
def upload(system_id):
    user_agent = request.headers.get("User-Agent", "Unknown")
    extractor, file_size, file_loc = extract()
    results = handle(extractor, system_id, config=config)
    response = handle_results(results, file_size, user_agent)
    extractor.cleanup()
    s3.save(file_loc, results["system"].get("system_id"), extractor.content_type)
    shutil.rmtree(os.path.dirname(file_loc))
    update_stats(results, user_agent)
    return response


@app.route("/r/insights/uploads/<system_id>", methods=["POST"])
def upload_legacy(system_id):
    return upload(system_id)


@app.route("/upload", methods=["POST"])
def upload_no_system_id():
    return upload(None)


@app.route("/")
def heartbeat():
    return "lub-dub"


def init():
    initialize_logging()

    for module in config["plugin_packages"]:
        plugins.load(module)


if __name__ == "__main__":
    init()
    if s3.s3_client is None:
        logger.warning("Archive persistence to S3 is disabled")
    app.run(host='127.0.0.1', port=config["port"])
