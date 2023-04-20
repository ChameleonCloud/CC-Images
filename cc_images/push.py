import contextlib
import logging
import multiprocessing
from datetime import datetime

import openstack
from openstack.image.v2.image import Image

from cc_images.image import ChameleonImage
from cc_images.sites import ChameleonSite

LOG = logging.getLogger(__name__)


def archive_name(old_image: Image, connection: openstack.connection.Connection) -> str:
    """
    Determines the archive name for an updated image. Essentially takes the base name,
    and concatenates a timestamp. If there is already an image with this name, appends
    a .counter to the end of the name until the name is unique
    """
    datetime_format = r"%Y-%m-%dT%H:%M:%SZ"
    old_image_timestamp = datetime.strptime(old_image.created_at, datetime_format)
    year = old_image_timestamp.year
    month = old_image_timestamp.month
    day = old_image_timestamp.day
    old_image_new_name = f"{old_image.name}-{year:04}{month:02}{day:02}"
    # If the new name has already been used,
    found_images_count = 1
    while connection.image.find_image(old_image_new_name, ignore_missing=True):
        old_image_new_name = (
            f"{old_image.name}-{year:04}{month:02}{day:02}.{found_images_count}"
        )
        found_images_count += 1
    return old_image_new_name


def do_push(
    image: ChameleonImage,
    site: ChameleonSite,
    should_wait_for_build: bool,
    semaphore: multiprocessing.Semaphore,
    is_built: multiprocessing.Condition,
) -> None:
    """
    Push a built image to Glance for all supported sites
    """
    if should_wait_for_build:
        LOG.info(f"PUSH {image.name}->{site.name}: Waiting for image to build...")
        with is_built:
            is_built.wait(timeout=60 * 60)

    with semaphore:
        LOG.info(f"PUSH {image.name}->{site.name}: Ready to push!")
        connection = openstack.connect(cloud=site.cloud)

        # Find all existing images with the same name under the desired project
        old_images = list(
            connection.image.images(
                name=image.name, owner=connection.current_project_id
            )
        )
        if len(old_images) > 1:
            raise ValueError(
                "Found more than one old image with the same name as the new image."
                " Please manually clear out redundant images."
            )
        old_image: Image | None = old_images[0] if old_images else None

        # The upload code is wrapped by a context guard to ensure that, if
        # uploading the new image fails, the old image will be un-archived.
        with contextlib.ExitStack() as guard:
            renamed_old_image = False
            new_image_failed = True

            if old_image:
                # If we're replacing an existing image, we need to archive it
                old_image_old_name = old_image.name

                def rollback_image_name():
                    if not (renamed_old_image and new_image_failed):
                        return
                    LOG.warning(
                        f"PUSH {image.name}->{site.name}: Uploading image failed! "
                        f"Rolling back archive..."
                    )
                    connection.image.update(old_image, name=old_image_old_name)
                    LOG.info(
                        f"PUSH {image.name}->{site.name}: " f"Restored old image name."
                    )

                guard.callback(rollback_image_name)

                LOG.info(
                    f"PUSH {image.name}->{site.name}: Found previous image "
                    f"from {old_image.created_at}."
                )
                LOG.info(f"PUSH {image.name}->{site.name}: Archiving old image...")
                old_image_new_name = archive_name(old_image, connection)

                LOG.info(
                    f"PUSH {image.name}->{site.name}: "
                    f"Renaming old image to {old_image_new_name}"
                )
                connection.image.update_image(old_image, name=old_image_new_name)
                renamed_old_image = True

            if site.is_baremetal:
                disk_format = "qcow2"
                file_path = image.qcow_path
            else:
                disk_format = "raw"
                file_path = image.raw_path

            if connection.current_project.name == "openstack":
                # If we're uploading via the openstack project,
                # then this is an official push
                visibility = "public"
            else:
                # If we're uploading via a non-admin project,
                # then we're just testing, so the image should be internal
                visibility = "shared"

            LOG.info(f"PUSH {image.name}->{site.name}: Uploading image...")
            connection.image.create_image(
                name=image.name,
                visibility=visibility,
                filename=file_path,
                disk_format=disk_format,
                container_format="bare",
                meta=image.metadata,
            )

            new_image_failed = False
            LOG.info(f"PUSH {image.name}->{site.name}: Finished pushing to Glance!")
