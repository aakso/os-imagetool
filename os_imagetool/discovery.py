from __future__ import print_function, unicode_literals

import datetime
import logging
import re
import rfc822
import urlparse
from collections import namedtuple

import requests

from os_imagetool.image import Image

LOG = logging.getLogger(__name__)


class ImageDiscoverer(object):
    def __init__(self, repository_url, basepath=None):
        self.repository_url = repository_url
        self.repository = {}
        self.basepath = basepath

    def refresh_repository(self, pattern=None):
        r = requests.get(self.repository_url)
        for line in r.iter_lines():
            parts = re.split(r' +', line)
            chksum = parts[0]
            image_name = parts[1]
            if pattern is not None and not re.search(pattern, image_name):
                continue
            if image_name.startswith('*'):
                image_name = image_name[1:]
            basepath = self.basepath if self.basepath else self.repository_url
            image = Image(
                name=image_name,
                size=None,
                last_modified=None,
                location=urlparse.urljoin(basepath, image_name),
                checksum=chksum)
            self.repository[image_name] = self.discover_image(image)

    def discover_image(self, image):
        sess = requests.Session()
        resp = sess.head(image.location)
        if resp.is_redirect:
            final_resp = None
            for final_resp in sess.resolve_redirects(resp, resp.request):
                pass
            resp = final_resp
        lastmodified = resp.headers.get('Last-Modified')
        if lastmodified:
            image.last_modified = datetime.datetime.fromtimestamp(
                rfc822.mktime_tz(rfc822.parsedate_tz(lastmodified)))
        size = resp.headers.get('Content-Length')
        if size:
            image.size = size
        image.location = resp.url
        return image

    def get_latest(self, pattern=None):
        images = (v for v in self.repository.itervalues())
        if pattern is not None:
            images = (v for v in images if re.search(pattern, v.name))
        images = sorted(images, key=lambda x: x.last_modified, reverse=True)
        if images:
            return images[0]
        else:
            return None


if __name__ == '__main__':
    import log
    import logging
    log.setup_logging()
    log.set_debug()
    l = ImageDiscoverer(
        'http://cloud.centos.org/centos/7/images/sha256sum.txt')
    print(l.get_latest(r'qcow2$'))
    print(l.get_latest())
