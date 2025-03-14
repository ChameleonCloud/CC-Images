import json
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


def object_exists(
        connection: openstack.connection.Connection,
        object_path: str,
) -> bool:
    object_parts = object_path.split("/", 1)
    if len(object_parts) < 2:
        raise ValueError("Object path must include container and path separated by /")
    container_name, object_name = object_parts

    if not container_exists(connection, container_name):
        return False

    objects = [obj.name for obj in connection.object_store.objects(container_name)]
    return object_name in objects


def create_container_if_not_exists(
        connection: openstack.connection.Connection,
        container: str,
) -> None:
    LOG.info(f"PUSH Checking if container exists: {container}")
    if not object_exists(connection, container):
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


def update_current(connection: openstack.connection.Connection,
                   container_name: str,
                   current_name: str,
                   image_name: str,
                   version_container: str,
                   max_retries: int = 3,
) -> None:
    LOG.info(f"PUSH {image_name}->{version_container}: Updating current value.")
    for attempt in range(max_retries):
        try:
            object = connection.get_object(
                container_name,
                current_name
            )
            if object is not None:
                headers, body = object
                manifest = json.loads(body)
                etag = headers.get('etag')
            else:
                manifest = {}
                etag = None

            manifest[image_name] = version_container

            conditional_param = {'if_match': etag} if etag else {'if_none_match': '*'}
            connection.object_store.create_object(
                container=container_name,
                name=current_name,
                data=json.dumps(manifest),
                **conditional_param
            )
        except openstack.exceptions.ConflictException:
            if attempt == max_retries - 1:
                raise RuntimeError("Failed to update current after 3 attempts")
            continue


def do_push(
    image: ChameleonImage,
    site: ChameleonSite,
    should_wait_for_build: bool,
    scope: str,
    version: str,
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

    date_str = datetime.now().strftime("%Y%m%d")
    version_str = f"{date_str}-{version}"
    with semaphore:
        LOG.info(f"PUSH {image.name}->{site.name}: Ready to push!")
        connection = openstack.connect(cloud=site.cloud)

        if not container_exists(connection, site.image_container):
            error = f"Container '{site.image_container}' must already exist."
            raise openstack.exceptions.ResourceNotFound(error)

        base_container_name = f"{site.image_container}/{scope}"
        current_name = f"{scope}/current"
        versions_path = f"{base_container_name}/versions"
        container_name = f"{versions_path}/{version_str}"
        full_manifest_path = f"{container_name}/{image.name}.manifest"

        if object_exists(connection, full_manifest_path):
            error = f"PUSH Manifest file '{full_manifest_path}' for the " + \
                    "image already exists, specify a new version to " + \
                    "upload this image again."
            LOG.error(error)
        else:
            create_container_if_not_exists(connection, container_name)

            push_object(connection,
                        image.provenance_path,
                        image.name + ".manifest",
                        site.name,
                        container_name)
            push_object(connection, image.qcow_path, image.name + ".qcow2", site.name, container_name)
            push_object(connection, image.raw_path, image.name + ".raw", site.name, container_name)

            update_current(connection, site.image_container, current_name, image.name, version_str)

            LOG.info(f"PUSH {image.name}->{site.name}: Finished uploading image!")
