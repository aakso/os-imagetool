from __future__ import print_function, unicode_literals

from urlparse import urlparse

import requests
import functools

from os_imagetool.errors import ImageToolError

DEFAULT_CHUNK_SIZE = 1024 * 1024

class Reader(object):
    def __init__(self, callback=None):
        self.callback = callback

    def iter_read(self, stream):
        for chunk in stream:
            if callable(self.callback):
                self.callback(chunk)
            yield chunk

    def bufread(self, file, chunk_size=DEFAULT_CHUNK_SIZE):
        while True:
            chunk = file.read(chunk_size)
            if chunk is None:
                raise StopIteration
            if callable(self.callback):
                self.callback(chunk)
            yield chunk

class Downloader(Reader):
    def __init__(self, chunk_size=DEFAULT_CHUNK_SIZE, *args, **kwargs):
        super(Downloader, self).__init__(*args, **kwargs)
        self.chunk_size = chunk_size

    def iter_download(self, url):
        parsed = urlparse(url)
        if parsed.scheme == 'file':
            stream = open(parsed.path, mode='rb')
        elif parsed.scheme == 'http' or parsed.scheme == 'https':
            res = requests.get(url, stream=True)
            if not res.ok:
                raise ImageToolError("non-ok response: {}".format(res))
            stream = res.iter_content(
                chunk_size=self.chunk_size)
        if getattr(stream, 'read'):
            method = functools.partial(self.bufread, chunk_size=self.chunk_size)
        else:
            method = self.iter_read

        for chunk in method(stream):
            yield chunk
