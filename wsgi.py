import os
from insights_web.util import initialize_logging
initialize_logging()

from insights_web.server import app as application
from insights.core import plugins

import logging

logger = logging.getLogger(__name__)

rule_packages = os.environ.get("RULE_PACKAGES")

if not rule_packages:
    logger.critical("RULE_PACKAGES must be defined")
    raise ValueError("RULE_PACKAGES must be defined")

for pkg in rule_packages.split(","):
    try:
        plugins.load(pkg)
    except:
        logger.exception("Failed to load %s", pkg)
