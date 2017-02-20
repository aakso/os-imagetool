from __future__ import print_function, unicode_literals

import argparse
import logging
import sys

import keystoneauth1.loading as loading

import os_imagetool.cli as cli
from os_imagetool.discovery import ImageDiscoverer
from os_imagetool.errors import ImageToolError
from os_imagetool.glance import GlanceClient
from os_imagetool.image import Image
from os_imagetool.log import set_debug, setup_logging

LOG = logging.getLogger('imagetool')


def run_tool(args):
    do_rotate = False

    if args.in_file:
        LOG.info("opening image file: %s", args.in_file)
        image = Image.from_file(args.in_file)
    elif args.repo:
        LOG.info("discovering image from %s", args.repo)
        disc = ImageDiscoverer(args.repo)
        disc.refresh_repository(pattern=args.repo_match_pattern)
        image = disc.get_latest()

    if args.out_file:
        if not image:
            raise ImageToolError("no in-image from repo or from file")
        LOG.info("in-image: %s", image)
        cli.download_image_to_file(image, args.out_file, args.verify)
    elif args.out_glance_name:
        if not image:
            raise ImageToolError("no in-image from repo or from file")
        LOG.info("in-image: %s", image)
        client = GlanceClient.from_argparse(args)
        imgid = cli.download_image_to_glance(
            client,
            image,
            args.out_glance_name,
            verify=args.verify,
            image_group=args.glance_image_group,
            disk_format=args.out_glance_disk_format,
            container_format=args.out_glance_container_format,
            force_upload=args.out_glance_force)
        do_rotate = (imgid is not None and args.glance_rotate is not None)

    if do_rotate or args.glance_rotate_force:
        if args.glance_rotate is None or args.glance_rotate < 0:
            raise ImageToolError("invalid value for glance_rotate")
        client = GlanceClient.from_argparse(args)
        cli.glance_rotate_images(
            client,
            args.glance_rotate,
            args.glance_image_group,
            suffix=args.glance_rotate_suffix,
            deactivate=args.glance_rotate_deactivate,
            delete=args.glance_rotate_delete)


def main():
    setup_logging()
    parser = argparse.ArgumentParser(
        description='Tool to handle image downloads and uploads')
    parser.add_argument('--in-file', metavar='FILE', help='local file to send')
    parser.add_argument(
        '--repo',
        metavar='URL',
        help='url to repo containing checksums and image names')
    parser.add_argument(
        '--repo-match-pattern',
        metavar='REGEXP',
        help='pattern to filter images with')
    parser.add_argument(
        '--out-file', metavar='FILE', help='file to save the image')
    parser.add_argument(
        '--out-glance-name', metavar='NAME', help='Name to use in Glance')
    parser.add_argument(
        '--out-glance-disk-format',
        metavar='NAME',
        default='qcow2',
        help='Disk format to use in Glance')
    parser.add_argument(
        '--out-glance-container-format',
        metavar='name',
        default='bare',
        help='Container format to use in glance')
    parser.add_argument(
        '--out-glance-force',
        action='store_true',
        help='Upload image to glance even if the same image already exists')
    parser.add_argument(
        '--glance-image-group',
        metavar='NAME',
        help='Group name to use in glance for upload and rotate')
    parser.add_argument(
        '--glance-rotate',
        metavar='NUM',
        type=int,
        help='Rotate images in glance by the image group, keep NUM amount of old images')
    parser.add_argument(
        '--glance-rotate-deactivate',
        action='store_true',
        help='Deactivate old images')
    parser.add_argument(
        '--glance-rotate-delete',
        action='store_true',
        help='Delete old images')
    parser.add_argument(
        '--glance-rotate-force',
        action='store_true',
        help='Rotate images even when we did not upload anything')
    parser.add_argument(
        '--glance-rotate-suffix',
        default='(OLD)',
        help='Rename old images. Add this suffix')
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify uploaded or downloaded image')

    loading.register_auth_argparse_arguments(parser, sys.argv)
    loading.session.register_argparse_arguments(parser)

    args = parser.parse_args()

    try:
        run_tool(args)
    except ImageToolError as e:
        print('ERROR: {}'.format(e), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('User interrupt')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
