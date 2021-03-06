from __future__ import print_function, unicode_literals

import datetime as dt
import hashlib
import logging
import math
import os
import sys
import time

import dateutil.parser as dp
import six

from os_imagetool.errors import ImageToolError
from os_imagetool.loader import DEFAULT_CHUNK_SIZE, Downloader, Reader

LOG = logging.getLogger(__name__)


def get_io_progress_cb(total_length=None, out=sys.stderr):
    class counter:
        percent = 0
        bytes_read = 0

    def cb(chunk):
        if total_length is None:
            return
        counter.bytes_read += len(chunk)
        current_percent = (math.floor(counter.bytes_read /
                                      float(total_length) * 10000) / 100)
        if out.isatty():
            # Emit status 10000 times using carriage return
            if counter.percent != current_percent:
                print(
                    '  {0} / {1} ({2:.2f}%)'.format(
                        counter.bytes_read, total_length, current_percent),
                    end="\r",
                    file=sys.stderr)
        else:
            # Emit status 100 times per line
            if math.floor(counter.percent) != math.floor(current_percent):
                print(
                    '  {0} / {1} ({2:.2f}%)'.format(
                        counter.bytes_read, total_length, current_percent),
                    end="\n",
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
                             min_disk=None,
                             min_ram=None,
                             properties=dict(),
                             force_upload=False,
                             visibility='private'):

    images = list(
        client.list(
            checksum=image.checksum, checksum_type=image.checksum_type))
    if len(images) > 0 and not force_upload:
        LOG.info("Image with checksum {} already exists, skipping".format(
            image.checksum))
        return None

    kwargs = properties
    if min_disk is not None:
        kwargs['min_disk'] = min_disk
    if min_ram is not None:
        kwargs['min_ram'] = min_ram
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
    print(file=sys.stderr)

    try:
        if verify and image.checksum is not None:
            hasher = get_hasher(image.checksum_type)
            LOG.info('starting to download image from glance for verify')
            stream = client.client.images.data(gimage.id, do_checksum=False)
            cb = get_io_progress_cb(total_length=image.size)
            reader = Reader(callback=cb)
            for chunk in reader.iter_read(stream):
                hasher.update(chunk)
            if image.checksum != hasher.hexdigest():
                raise ImageToolError('Image verify failed')
            print(file=sys.stderr)
    except:
        client.client.images.delete(gimage.id)
        LOG.error('verify failed, deleted image %s', gimage.id)
        six.reraise(*sys.exc_info())

    print(gimage.id)
    return gimage.id


def glance_rotate_images(client,
                         num,
                         image_group,
                         latest_suffix=None,
                         rotated_suffix=None,
                         deactivate=False,
                         delete=False,
                         hide=False,
                         visibility='private'):
    images = client.list(image_group=image_group)
    images = sorted(
        images, key=lambda x: dp.parse(x['created_at']), reverse=True)

    for i, image in enumerate(images):
        newprops = dict()
        # Latest image
        if i == 0:
            # Add suffix if required
            if latest_suffix is not None and not image.name.endswith(
                    latest_suffix):
                newname = ' '.join([image.get(client.PROP_ORIGINAL_NAME,
                                              image.name), latest_suffix])
                newprops.update(name=newname)
            if not image.get(client.PROP_IS_LATEST) == 'True':
                newprops[client.PROP_IS_LATEST] = 'True'

        # Not latest image
        elif i > 0:
            # Add timestamp and suffix if required
            if not image.get(client.PROP_ROTATED):
                newprops[client.PROP_ROTATED] = dt.datetime(*time.gmtime(
                )[:7]).isoformat() + 'Z'
            if rotated_suffix is not None and not image.name.endswith(
                    rotated_suffix):
                newprops.update(name=' '.join([image.get(
                    client.PROP_ORIGINAL_NAME, image.name), rotated_suffix]))
            if not image.get(client.PROP_IS_LATEST) == 'False':
                newprops[client.PROP_IS_LATEST] = 'False'

        # Ensure desired visibility level for all images
        if image.visibility != visibility:
            newprops.update(visibility=visibility)

        # Handle images you want to delete/deactivate/hide
        if i > num:
            if hide:
                newprops.pop('visibility', None)
                if image.visibility != 'community':
                    newprops.update(visibility='community')
            if deactivate and image.status == 'active':
                LOG.info('Deactivating image %s', image.id)
                client.client.images.deactivate(image.id)
            if delete:
                LOG.info('Deleting image %s', image.id)
                client.client.images.delete(image.id)
                continue
        if newprops:
            for k, v in newprops.items():
                LOG.info("Image: %s update %s: %s -> %s", image.id, k,
                         image.get(k), v)
            client.client.images.update(image.id, **newprops)


def download_image_to_file(image, out_file, verify=False, force=False):
    cb = get_io_progress_cb(total_length=image.size)
    loader = Downloader(callback=cb)
    hasher = get_hasher(image.checksum_type)
    # Check if image already exists
    if os.path.isfile(out_file) and not force:
        with open(out_file, 'r') as f:
            while True:
                buf = f.read(DEFAULT_CHUNK_SIZE)
                if not buf: break
                hasher.update(buf)
            if hasher.hexdigest() == image.checksum:
                LOG.info("Image with checksum {} already exists, skipping".
                         format(image.checksum))
                return
        hasher = get_hasher(image.checksum_type)

    with open(out_file, 'w') as f:
        LOG.info('starting to download {} -> {}'.format(image.location,
                                                        out_file))
        for data in loader.iter_download(image.location):
            f.write(data)
        print(file=sys.stderr)
        LOG.info("Download done")
    if verify:
        with open(out_file, 'r') as f:
            while True:
                buf = f.read(DEFAULT_CHUNK_SIZE)
                if not buf: break
                hasher.update(buf)
            if hasher.hexdigest() != image.checksum:
                raise ImageToolError('Image verify failed')
            else:
                LOG.info('Image verify ok')
    print(os.path.abspath(out_file))
