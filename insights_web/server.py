import logging
import time
import platform
import insights
import uuid
import tempfile
import os
import shutil
import pkgutil
from collections import defaultdict
from flask import Flask, json, request, jsonify

from insights.core import archives, dr
from insights.core.evaluators import InsightsEvaluator, SingleEvaluator
from insights.settings import web as config
from insights_web import s3, util

stats = defaultdict(int)
stats["start_time"] = time.time()

app = Flask(__name__)

MAX_UPLOAD_SIZE = 1024 * 1024 * 100

logger = logging.getLogger(__name__)

package_info = dict.fromkeys(["RELEASE", "COMMIT", "VERSION", "NAME"])

for name in package_info:
    package_info[name] = pkgutil.get_data(__name__, name).strip()


def get_nvr():
    return "{0}-{1}-{2}".format(package_info["NAME"],
                                package_info["VERSION"],
                                package_info["RELEASE"])


def format_seconds(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return "%02d:%02d:%02d" % (h, m, s)


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


def create_evaluator(tmp_dir, system_id):
    from insights.core.hydration import create_context

    broker = dr.Broker()
    ctx = create_context(tmp_dir)
    broker[ctx.__class__] = ctx
    if system_id:
        return InsightsEvaluator(broker=broker, system_id=system_id)
    return SingleEvaluator(broker=broker)


def extract():
    if "file" not in request.files:
        raise EngineError("No 'file' key found in form part", 400)
    file_loc = os.path.join(tempfile.mkdtemp(), "tmp.tar.gz")
    request.files["file"].save(file_loc)
    file_size = os.stat(file_loc).st_size
    verify_file_size(file_size)
    return file_size, file_loc


def handle(tmp_dir, system_id=None, account=None, config=None):
    return create_evaluator(tmp_dir, system_id).process()


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
        versions["insights-web"] = {"version": get_nvr(),
                                    "commit": package_info["COMMIT"]}
        versions.update(insights.RULES_STATUS)
    stats["uptime"] = format_seconds(time.time() - stats["start_time"])
    return jsonify(stats)


@app.route("/upload/<system_id>", methods=["POST"])
def upload(system_id):
    user_agent = request.headers.get("User-Agent", "Unknown")
    setattr(util.thread_context, "request_id", request.headers.get("X-Request-Id", "Unknown"))
    account_number = request.headers.get("X-Account", "")
    file_size, file_loc = extract()
    with archives.extract(file_loc) as ex:
        results = handle(ex.tmp_dir, system_id, config=config)
        response = handle_results(results, file_size, user_agent)
    s3.save(file_loc, results["system"].get("system_id"), ex.content_type, account_number)
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
    util.initialize_logging()
    for module in config["plugin_packages"]:
        dr.load_components(module)


if __name__ == "__main__":
    init()
    if s3.s3_client is None:
        logger.warning("Archive persistence to S3 is disabled")
    app.run(host='127.0.0.1', port=config["port"])
