from __future__ import unicode_literals

import os
import datetime
import hashlib

from os_imagetool.loader import DEFAULT_CHUNK_SIZE

class Image(object):
    def __init__(self, name=None, checksum=None, checksum_type=None, location=None, size=None, last_modified=None):
        self.name = name
        if checksum:
            self.checksum = str(checksum)
        self._checksum_type = checksum_type
        self.location = location
        self.size = size
        self.last_modified = last_modified

    @classmethod
    def from_file(cls, path, checksum_type='sha256'):
        hasher = getattr(hashlib, checksum_type)()
        stat = os.stat(path)
        with open(path, 'r') as f:
            image = cls(
                name=os.path.basename(path),
                size=stat.st_size,
                location='file://{}'.format(os.path.abspath(path)),
                last_modified=datetime.datetime.fromtimestamp(stat.st_mtime)
            )
            while True:
                buf = f.read(DEFAULT_CHUNK_SIZE)
                if not buf: break
                hasher.update(buf)
            image.checksum = hasher.hexdigest()
        return image

    @property
    def checksum(self):
        return self._checksum

    @checksum.setter
    def checksum(self, value):
        self._checksum = value.lower()

    @property
    def checksum_type(self):
        if self._checksum_type is None:
            return self._detect_checksum_type()
        return self._checksum_type

    @checksum_type.setter
    def checksum_type(self, value):
        self._checksum_type = value

    def _detect_checksum_type(self):
        if self.checksum is None:
            return None
        if len(self.checksum) == 32:
            return 'md5'
        if len(self.checksum) == 40:
            return 'sha1'
        if len(self.checksum) == 56:
            return 'sha224'
        if len(self.checksum) == 64:
            return 'sha256'
        if len(self.checksum) == 96:
            return 'sha384'
        if len(self.checksum) == 128:
            return 'sha512'

    def __repr__(self):
        return '<Image name={} checksum={} checksum_type={} location={} last_modified="{}" size={}>'.format(
            self.name,
            self.checksum,
            self.checksum_type,
            self.location,
            self.last_modified,
            self.size
        )
