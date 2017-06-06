import os
import logging
import time
import platform
import falafel
import shutil
import tempfile
import uuid
from flask import Flask, json, request, jsonify
from collections import defaultdict
from falafel.settings import web as config
from falafel.core import plugins
from . import tar_processor

stats = defaultdict(int)
stats["start_time"] = time.time()

app = Flask(__name__)

MAX_UPLOAD_SIZE = 1024 * 1024 * 100

logger = logging.getLogger(__name__)


try:
    import logstash
except:
    logstash_enabled = False
else:
    logstash_enabled = True


def format_seconds(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return "%02d:%02d:%02d" % (h, m, s)


def configure_logger(logger, log_type, propagate=True):
    l = logging.getLogger(logger)
    l.propagate = propagate
    if len(l.handlers) != 0:
        return
    l.setLevel(config["log_level"])
    handler = logstash.LogstashHandler(config["logstash_host"], config["logstash_port"],
                                       version=1, message_type=log_type)
    l.addHandler(handler)


def initialize_logging():
    if logstash_enabled and config["distributed"]:
        configure_logger("", config["log_type"])
    else:
        logging.basicConfig()
        logging.getLogger("").setLevel(config["log_level"])
    logging.getLogger("statsd").setLevel(logging.FATAL)


class EngineError(Exception):
    def __init__(self, message, status_code=500):
        super(EngineError, self).__init__(message)
        self.status_code = status_code


@app.errorhandler(EngineError)
def handle_error(error):
    return error.message, error.status_code, None


@app.route("/status")
def status():
    if "versions" not in stats:
        versions = stats["versions"] = {}
        versions["falafel"] = {"version": falafel.get_nvr(),
                               "commit": falafel.package_info["COMMIT"]}
        versions.update(falafel.RULES_STATUS)
    stats["uptime"] = format_seconds(time.time() - stats["start_time"])
    return jsonify(stats)


def get_file_size(file_loc):
    file_size = os.stat(file_loc).st_size
    if file_size > MAX_UPLOAD_SIZE:
        error_msg = "Upload is too big. %s/%s bytes" % (file_size, MAX_UPLOAD_SIZE)
        raise EngineError(error_msg, 413)
    if file_size == 0:
        raise EngineError("Upload has an empty archive body.", 400)
    return file_size


def save_file():
    if "file" not in request.files:
        raise EngineError("No 'file' key found in form part", 400)
    file_loc = os.path.join(tempfile.mkdtemp(), "tmp.tar.gz")
    request.files["file"].save(file_loc)
    return file_loc


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


@app.route("/upload/<system_id>", methods=["POST"])
def upload(system_id):
    user_agent = request.headers.get("User-Agent", "Unknown")
    file_loc = save_file()
    file_size = get_file_size(file_loc)
    results = tar_processor.handle(file_loc, system_id, config=config)
    shutil.rmtree(os.path.dirname(file_loc))
    response = handle_results(results, file_size, user_agent)
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
    logger.info("Starting Insights Engine (tornado) on port %s" % config["port"])
    app.run(host='0.0.0.0', port=config["port"])
