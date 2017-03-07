from __future__ import print_function, unicode_literals

import argparse
import logging
import os
import sys
import signal

import keystoneauth1.loading as loading

import os_imagetool.cli as cli
from os_imagetool.discovery import ImageDiscoverer
from os_imagetool.errors import ImageToolError
from os_imagetool.glance import GlanceClient
from os_imagetool.image import Image
from os_imagetool.log import set_debug, setup_logging

LOG = logging.getLogger('imagetool')


# Treat SIGTERM as interrupt so we can abort this tool 
# cleanly for example in Jenkins
def sigterm(s, f):
    raise KeyboardInterrupt('SIGTERM')


signal.signal(signal.SIGTERM, sigterm)


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
        cli.download_image_to_file(
            image,
            args.out_file,
            verify=args.verify,
            force=args.out_file_force)
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
            min_disk=args.out_glance_min_disk,
            min_ram=args.out_glance_min_ram,
            properties=dict(args.out_glance_properties),
            force_upload=args.out_glance_force,
            visibility=args.out_glance_visibility)
        do_rotate = (imgid is not None and args.glance_rotate is not None)

    if do_rotate or args.glance_rotate_force:
        if args.glance_rotate is None or args.glance_rotate < 0:
            raise ImageToolError("invalid value for glance_rotate")
        client = GlanceClient.from_argparse(args)
        cli.glance_rotate_images(
            client,
            args.glance_rotate,
            args.glance_image_group,
            latest_suffix=args.glance_rotate_latest_suffix,
            rotated_suffix=args.glance_rotate_old_suffix,
            deactivate=args.glance_rotate_deactivate,
            delete=args.glance_rotate_delete,
            visibility=args.glance_rotate_visibility)


def main():
    setup_logging()
    parser = argparse.ArgumentParser(
        description='Tool to handle image downloads and uploads')
    parser.add_argument(
        '--in-file',
        default=os.environ.get('IMAGETOOL_IN_FILE'),
        metavar='FILE',
        help='local file to send')
    parser.add_argument(
        '--repo',
        metavar='URL',
        default=os.environ.get('IMAGETOOL_REPO'),
        help='url to repo containing checksums and image names')
    parser.add_argument(
        '--repo-match-pattern',
        metavar='REGEXP',
        default=os.environ.get('IMAGETOOL_REPO_MATCH_PATTERN'),
        help='pattern to filter images with')
    parser.add_argument(
        '--out-file',
        metavar='FILE',
        default=os.environ.get('IMAGETOOL_OUT_FILE'),
        help='file to save the image')
    parser.add_argument(
        '--out-file-force',
        action='store_true',
        default=parse_bool('IMAGETOOL_OUT_FILE_FORCE'),
        help='Download image to file even if the same image already exists')
    parser.add_argument(
        '--out-glance-name',
        metavar='NAME',
        default=os.environ.get('IMAGETOOL_OUT_GLANCE_NAME'),
        help='Name to use in Glance')
    parser.add_argument(
        '--out-glance-disk-format',
        metavar='NAME',
        default=os.environ.get('IMAGETOOL_OUT_DISK_FORMAT', 'qcow2'),
        help='Disk format to use in Glance')
    parser.add_argument(
        '--out-glance-container-format',
        metavar='name',
        default=os.environ.get('IMAGETOOL_OUT_CONTAINER_FORMAT', 'bare'),
        help='Container format to use in glance')
    parser.add_argument(
        '--out-glance-min-disk',
        metavar='GB',
        type=int,
        default=[os.environ.get('IMAGETOOL_OUT_GLANCE_MIN_DISK')],
        help='Optional minimum disk size required for the image in gigabytes')
    parser.add_argument(
        '--out-glance-min-ram',
        metavar='MB',
        type=int,
        default=os.environ.get('IMAGETOOL_OUT_GLANCE_MIN_RAM'),
        help='Optional minimum ram size required for the image in megabytes')
    parser.add_argument(
        '--out-glance-properties',
        metavar='KEY=VAL,KEY=VAL,..',
        default=os.environ.get('IMAGETOOL_OUT_GLANCE_PROPERTY'),
        help='Additional image properties to set')
    parser.add_argument(
        '--out-glance-force',
        action='store_true',
        default=parse_bool('IMAGETOOL_OUT_GLANCE_FORCE'),
        help='Upload image to glance even if the same image already exists')
    parser.add_argument(
        '--out-glance-visibility',
        metavar='name',
        default=os.environ.get('IMAGETOOL_OUT_GLANCE_VISIBILITY', 'private'),
        help='Set uploaded image visibility to this value')
    parser.add_argument(
        '--glance-image-group',
        metavar='NAME',
        default=os.environ.get('IMAGETOOL_GLANCE_IMAGE_GROUP'),
        help='Group name to use in glance for upload and rotate')
    parser.add_argument(
        '--glance-rotate',
        metavar='NUM',
        type=int,
        default=(lambda x=os.environ.get('IMAGETOOL_GLANCE_ROTATE'): int(x) if x else None)(),
        help='Rotate images in glance by the image group, keep NUM amount of old images')
    parser.add_argument(
        '--glance-rotate-deactivate',
        action='store_true',
        default=parse_bool('IMAGETOOL_GLANCE_ROTATE_DEACTIVATE'),
        help='Deactivate old images')
    parser.add_argument(
        '--glance-rotate-delete',
        action='store_true',
        default=parse_bool('IMAGETOOL_GLANCE_ROTATE_DELETE'),
        help='Delete old images')
    parser.add_argument(
        '--glance-rotate-force',
        action='store_true',
        default=parse_bool('IMAGETOOL_GLANCE_ROTATE_FORCE'),
        help='Rotate images even when we did not upload anything')
    parser.add_argument(
        '--glance-rotate-latest-suffix',
        default=os.environ.get('IMAGETOOL_GLANCE_ROTATE_LATEST_SUFFIX'),
        help='Rename latest image. Add this suffix')
    parser.add_argument(
        '--glance-rotate-old-suffix',
        default=os.environ.get('IMAGETOOL_GLANCE_ROTATE_OLD_SUFFIX'),
        help='Rename old images. Add this suffix')
    parser.add_argument(
        '--glance-rotate-visibility',
        metavar='name',
        default=os.environ.get('IMAGETOOL_GLANCE_ROTATE_VISIBILITY',
                               'private'),
        help='Set latest image visibility to this value')
    parser.add_argument(
        '--verify',
        action='store_true',
        default=parse_bool('IMAGETOOL_VERIFY'),
        help='Verify uploaded or downloaded image')

    loading.register_auth_argparse_arguments(parser, sys.argv)
    loading.session.register_argparse_arguments(parser)

    args = parser.parse_args()

    try:
        # Parse ['key1=val', 'key2=val,key3=val']
        if args.out_glance_properties:
            props = args.out_glance_properties[:]
            args.out_glance_properties = [parse_kvs(item) for item in parse_list(props)]

        run_tool(args)
    except ImageToolError as e:
        print('ERROR: {}'.format(e), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('User interrupt')
        return 1
    return 0

def parse_bool(var):
    val = os.environ.get(var)
    if val and val.lower() in ['true', 't', '1']:
        return True
    else:
        return False

def parse_list(var):
    if var:
        return var.split(',')
    else:
        return []

def parse_kvs(var):
    p = var.split('=')
    if len(p) == 2:
        return (p[0].strip(), p[1].strip())
    else:
        raise ImageToolError('cannot parse {}'.format(var))

if __name__ == '__main__':
    sys.exit(main())
