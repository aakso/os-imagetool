import logging
import sys

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='[%(name)-18s] %(levelname)-8s %(message)s',
        stream=sys.stderr
    )

def set_debug():
    logging.getLogger('').setLevel(logging.DEBUG)