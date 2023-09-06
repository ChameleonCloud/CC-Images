#!/usr/bin/env python3

"""
This script acts as a wrapper around disk-image-create. Any configuration for disk-image-create
will be passed along to it, but this wrapper provides a convenient interface for executing builds
of Chameleon images.
"""
import contextlib
import logging
import os
import pprint
import signal
import stat
import sys
import time
from datetime import datetime

from cc_images.args import parse_args
from cc_images.config import BUILD_PATH
from cc_images.image import resolve_image_hierarchy
from cc_images.tasks import run_tasks

start_time = datetime.now()
LOG = logging.getLogger(__name__)


def restore_ownership(path: str, uid: int, gid: int) -> None:
    original_mode = os.stat(path).st_mode
    # Set ownership to original user who ran the script
    os.chown(path, uid, gid)
    # Allow owner to read/write the file
    os.chmod(path, original_mode | stat.S_IRUSR | stat.S_IWUSR)


cmdline = parse_args()

# These variables are for informing the subprocess running as root
# who originally ran the script
CC_IMAGES_PARENT_UID_ENV = "CC_IMAGES_PARENT_UID"
CC_IMAGES_PARENT_GID_ENV = "CC_IMAGES_PARENT_GID"
# Handle required permissions
if not os.geteuid() == 0:
    LOG.warning(
        "This script needs to be run as root in order for disk-image-create to work."
    )
    time.sleep(1)
    os.execve(
        "/usr/bin/sudo",
        ["-E", "-S", sys.executable, *sys.argv],
        os.environ
        | {
            CC_IMAGES_PARENT_UID_ENV: str(os.getuid()),
            CC_IMAGES_PARENT_GID_ENV: str(os.getgid()),
        },
    )


def _restore_build_ownership():
    """
    Sets ownership of all build files to the original user who ran the script
    """
    if os.geteuid() == 0:
        parent_uid = int(os.getenv(CC_IMAGES_PARENT_UID_ENV, 0))
        parent_gid = int(os.getenv(CC_IMAGES_PARENT_GID_ENV, 0))
        if parent_uid:
            LOG.info("Restoring ownership of build artifacts.")
            for root, dirs, files in os.walk(BUILD_PATH):
                for d in dirs:
                    restore_ownership(os.path.join(root, d), parent_uid, parent_gid)
                for f in files:
                    restore_ownership(os.path.join(root, f), parent_uid, parent_gid)


LOG.info(
    f"Configured with the following architectures: {[arch.name for arch in cmdline.arch]}"
)
LOG.info(f"Configured with the following images: {cmdline.images}")

images_to_run = resolve_image_hierarchy(cmdline)

LOG.info(f"Running with the following images:\n{pprint.pformat(images_to_run)}")

with contextlib.ExitStack() as guard:
    # Ensure that build dir is not owned by root regardless of what happens
    guard.callback(_restore_build_ownership)
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):

        def _sighandle(signum, *_):
            _restore_build_ownership()
            sys.exit(signum)

        signal.signal(sig, _sighandle)
    run_tasks(cmdline, images_to_run)

LOG.info(f"Finished in {datetime.now() - start_time}")
