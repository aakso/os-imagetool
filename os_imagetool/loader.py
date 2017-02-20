from __future__ import print_function, unicode_literals

from urlparse import urlparse

import requests


class Reader(object):
    def __init__(self, callback=None):
        self.callback = callback

    def iter_read(self, stream):
        for chunk in stream:
            if callable(self.callback):
                self.callback(chunk)
            yield chunk


class Downloader(Reader):
    def __init__(self, chunk_size=101024, *args, **kwargs):
        super(Downloader, self).__init__(*args, **kwargs)
        self.chunk_size = chunk_size

    def iter_download(self, url):
        parsed = urlparse(url)
        if parsed.scheme == 'file':
            stream = open(parsed.path, 'r')
        elif parsed.scheme == 'http' or parsed.scheme == 'https':
            stream = requests.get(url, stream=True).iter_content(
                chunk_size=self.chunk_size)
        for chunk in self.iter_read(stream):
            yield chunk
