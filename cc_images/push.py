import logging
import multiprocessing
import tempfile
from datetime import datetime

import openstack

from cc_images.image import ChameleonImage
from cc_images.sites import ChameleonSite


LOG = logging.getLogger(__name__)


def container_exists(
        connection: openstack.connection.Connection,
        container: str,
) -> bool:
    containers = [c.name for c in connection.object_store.containers()]
    return container in containers


def create_container_if_not_exists(
        connection: openstack.connection.Connection,
        container: str,
) -> None:
    LOG.info(f"PUSH Checking if container exists: {container}")
    if not container_exists(connection, container):
        connection.object_store.create_container(name=container)
        LOG.info(f"PUSH Created container: '{container}'.")
    else:
        LOG.info(f"PUSH Container '{container}' already exists.")


def push_object(connection: openstack.connection.Connection,
                object_path: str,
                file_name: str,
                site_name: str,
                container_name: str,
) -> None:
    LOG.info(f"PUSH Uploading: {file_name}->{site_name}:{container_name}")
    connection.create_object(
            container=container_name,
            name=file_name,
            filename=object_path,
    )


def do_push(
    image: ChameleonImage,
    site: ChameleonSite,
    should_wait_for_build: bool,
    scope: str,
    semaphore: multiprocessing.Semaphore,
    is_built: multiprocessing.Condition,
) -> None:
    """
    Push a built image to Swift for all supported sites
    """
    if should_wait_for_build:
        LOG.info(f"PUSH {image.name}->{site.name}({scope}): Waiting for image to build...")
        with is_built:
            is_built.wait(timeout=60 * 60)

    date_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    with semaphore:
        LOG.info(f"PUSH {image.name}->{site.name}: Ready to push!")
        connection = openstack.connect(cloud=site.cloud)

        if not container_exists(connection, site.image_container):
            error = f"Container '{site.image_container}' must already exist."
            raise openstack.exceptions.ResourceNotFound(error)

        container_name = f"{site.image_container}/{scope}/{date_timestamp}"
        create_container_if_not_exists(connection, container_name)

        push_object(connection,
                    image.provenance_path,
                    image.name + ".manifest",
                    site.name,
                    container_name)
        push_object(connection, image.qcow_path, image.name + ".qcow2", site.name, container_name)
        push_object(connection, image.raw_path, image.name + ".raw", site.name, container_name)

        with tempfile.NamedTemporaryFile(delete=True) as temp_file:
            temp_file.write((date_timestamp + "\n").encode('utf-8'))
            temp_file.flush()
            push_object(connection, temp_file.name, "current", site.name, container_name)

        LOG.info(f"PUSH {image.name}->{site.name}: Finished uploading images!")
