from __future__ import print_function, unicode_literals

import logging
import sys

import glanceclient.common.http as glance_http
import keystoneauth1.loading as ksloading
import six
from glanceclient.v2.client import Client
from keystoneauth1.session import Session

from os_imagetool.errors import ImageToolError
from os_imagetool.loader import DEFAULT_CHUNK_SIZE

LOG = logging.getLogger(__name__)

# Override glance chunk size with our default for performance
# Too bad they don't expose this
glance_http.CHUNKSIZE = DEFAULT_CHUNK_SIZE

class GlanceChunkAdapter(object):
    def __init__(self, stream):
        self.stream = stream

    def read(self, size):
        try:
            return next(self.stream)
        except StopIteration:
            return None


class GlanceClient(object):
    PROP_IMAGE_GROUP = '_image_group'
    PROP_CHECKSUM = '_checksum_{}'
    PROP_ROTATED = '_rotated'
    PROP_ORIGINAL_NAME = '_orig_name'
    PROP_IS_LATEST = '_is_latest'

    @classmethod
    def from_argparse(cls, args):
        auth = ksloading.cli.load_from_argparse_arguments(args)
        session = Session(auth=auth)
        return cls(session)

    def __init__(self, session):
        self.client = Client(session=session)

    def list(self,
             checksum=None,
             checksum_type=None,
             image_group=None,
             **qfilter):
        images = self.client.images.list(filters=qfilter)

        if image_group:
            images = (x for x in images
                      if x.get(self.PROP_IMAGE_GROUP) == image_group)

        if checksum:
            if checksum_type is None:
                raise ImageToolError('checksum_type required')
            k = self.PROP_CHECKSUM.format(checksum_type)
            images = (x for x in images if x.get(k) == checksum)

        return images

    def upload_image(self, image_name, stream, **kwargs):
        kwargs[self.PROP_ORIGINAL_NAME] = image_name
        image = self.client.images.create(name=image_name, **kwargs)
        LOG.info('created image: {}'.format(image.id))
        try:
            self.client.images.upload(image.id, GlanceChunkAdapter(stream))
        except:
            self.client.images.delete(image.id)
            LOG.error('cleanup image: {}'.format(image.id))
            six.reraise(*sys.exc_info())
        return image
