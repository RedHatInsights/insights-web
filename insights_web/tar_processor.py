#!/usr/bin/env python

import os
import json
import logging

from insights import util
from insights.core import archives, specs, evaluators
from insights.core.archives import InvalidArchive

logger = logging.getLogger(__name__)
uploader_logger = logging.getLogger("upload_client")


def handle(filename, system_id=None, account=None, config=None):
    try:
        return _handle(filename, system_id, account, config)
    except InvalidArchive:
        raise
    except:
        logger.exception("Exception encountered during _handle")
        raise


class UploaderLogEvaluator(evaluators.InsightsEvaluator):

    def post_process(self):
        uploader_log_content = self.spec_mapper.get_content("uploader_log")
        if uploader_log_content:
            path = util.get_path_for_system_id("uploader_log", self.system_id) + ".log"
            util.ensure_dir(path, dirname=True)
            with open(path, 'w') as log_fp:
                log_fp.write("\n".join(uploader_log_content))
                log_url = "%s/uploader_logs/%s" % (util.get_addr(), self.system_id)
                logger.info("Uploader Log for system [%s] is available: %s", self.system_id, log_url)


class SoSReportEvaluator(evaluators.SingleEvaluator):

    def format_response(self, response):
        evaluators.serialize_skips(response["skips"])
        return response


def _handle(filename, system_id=None, account=None, config=None):
    with archives.TarExtractor() as ex:

        arc = ex.from_path(filename)
        os.unlink(filename)
        spec_mapper = specs.SpecMapper(arc)

        md_str = spec_mapper.get_content("metadata.json", split=False, default="{}")
        md = json.loads(md_str)

        if md and 'systems' in md:
            runner = evaluators.InsightsMultiEvaluator(spec_mapper, system_id, md)
        elif spec_mapper.get_content("machine-id"):
            runner = UploaderLogEvaluator(spec_mapper, system_id=system_id)
        else:
            runner = SoSReportEvaluator(spec_mapper)
        return runner.process()
