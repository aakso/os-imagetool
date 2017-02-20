from __future__ import print_function, unicode_literals

import datetime as dt
import hashlib
import logging
import math
import os
import sys
import time

import dateutil.parser as dp

from os_imagetool.errors import ImageToolError
from os_imagetool.loader import Downloader, Reader

LOG = logging.getLogger(__name__)


def get_io_progress_cb(total_length=None):
    class counter:
        percent = 0
        bytes_read = 0

    def cb(chunk):
        counter.bytes_read += len(chunk)
        current_percent = (math.floor(counter.bytes_read /
                                      float(total_length) * 10000) / 100)
        if counter.percent != current_percent:
            print(
                '  {0} / {1} ({2:.2f}%)'.format(counter.bytes_read,
                                                total_length, current_percent),
                end="\r",
                file=sys.stderr)
            counter.percent = current_percent

    return cb


def get_hasher(algo):
    try:
        return getattr(hashlib, algo)()
    except AttributeError:
        raise ImageToolError('Verify not possible, algo {} unavailable'.format(
            algo))


def download_image_to_glance(client,
                             image,
                             name,
                             verify=False,
                             image_group=None,
                             disk_format='qcow2',
                             container_format='bare',
                             force_upload=False):

    images = list(
        client.list(
            checksum=image.checksum, checksum_type=image.checksum_type))
    if len(images) > 0 and not force_upload:
        LOG.info("Image with checksum {} already exists, skipping".format(
            image.checksum))
        return None

    kwargs = dict()
    if image_group is not None:
        kwargs['_image_group'] = image_group

    if image.checksum is not None and image.checksum_type is not None:
        kwargs['_checksum_{}'.format(image.checksum_type)] = image.checksum

    cb = get_io_progress_cb(total_length=image.size)
    loader = Downloader(callback=cb)
    stream = loader.iter_download(image.location)
    LOG.info('uploading to glance %s -> %s', image.location, name)
    gimage = client.upload_image(
        name,
        stream,
        disk_format=disk_format,
        container_format=container_format,
        **kwargs)
    print()

    if verify and image.checksum is not None:
        hasher = get_hasher(image.checksum_type)
        LOG.info('starting to download image from glance for verify')
        stream = client.client.images.data(gimage.id, do_checksum=False)
        cb = get_io_progress_cb(total_length=image.size)
        reader = Reader(callback=cb)
        for chunk in reader.iter_read(stream):
            hasher.update(chunk)
        if image.checksum != hasher.hexdigest():
            client.client.images.delete(gimage.id)
            LOG.error('verify failed, deleted image %s', gimage.id)
            raise ImageToolError('Image verify failed')
        print()
    print(gimage.id)
    return gimage.id


def glance_rotate_images(client,
                         num,
                         image_group,
                         suffix='(OLD)',
                         deactivate=False,
                         delete=False):
    images = client.list(image_group=image_group)
    images = sorted(
        images, key=lambda x: dp.parse(x['created_at']), reverse=True)
    i = 1
    for image in images[1:]:
        if not image.get(client.PROP_ROTATED):
            newprops = dict()
            newprops[client.PROP_ROTATED] = dt.datetime(
                *time.gmtime()[:7]).isoformat() + 'Z'
            newprops['name'] = ' '.join([image.name, suffix])
            LOG.info('Renaming image %s: %s -> %s', image.id, image.name,
                     newprops['name'])
            client.client.images.update(image.id, **newprops)
        if i > num:
            if deactivate and image.status == 'active':
                LOG.info('Deactivating image %s', image.id)
                client.client.images.deactivate(image.id)
            elif delete:
                LOG.info('Deleting image %s', image.id)
                client.client.images.delete(image.id)


def download_image_to_file(image, out_file, verify=False):
    cb = get_io_progress_cb(total_length=image.size)
    loader = Downloader(callback=cb)
    if verify:
        hasher = get_hasher(image.checksum_type)
    with open(out_file, 'w') as f:
        LOG.info('starting to download {} -> {}'.format(image.location,
                                                        out_file))
        for data in loader.iter_download(image.location):
            f.write(data)
        print()
        LOG.info("Download done")
    if verify:
        with open(out_file, 'r') as f:
            while True:
                buf = f.read(65536)
                if not buf: break
                hasher.update(buf)
            if hasher.hexdigest() != image.checksum:
                raise ImageToolError('Image verify failed')
            else:
                LOG.info('Image verify ok')
    print(os.path.abspath(out_file))
