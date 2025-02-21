import logging
import multiprocessing
import os
import pprint
import subprocess
import sys

from cc_images.config import ELEMENTS_PATH
from cc_images.image import ChameleonImage
from cc_images.third_party import THIRD_PARTY_ELEMENT_SOURCES

LOG = logging.getLogger(__name__)


def do_build(
    image: ChameleonImage,
    deps: "list[multiprocessing.Condition]",
    semaphore: multiprocessing.Semaphore,
    finished_building: multiprocessing.Condition,
) -> None:
    """
    Configures and runs disk-image-create to run for a single image. Waits on all dependencies
    to finish building first, and then alerts its dependencies when the build is complete.

    This function is quite destructive, as it overwrites a bunch of system stuff to ensure
    disk-image-create runs correctly. It should only be run inside a worker process.
    """
    if deps:
        LOG.info(
            f"BUILD {image.name}: Awaiting for {len(deps)} required dependencies to build."
        )
        for dep in deps:
            # Wait for all parent tasks to complete
            with dep:
                dep.wait(timeout=60 * 60)
        LOG.info(f"BUILD {image.name}: Image dependencies complete.")

    LOG.info(f"BUILD {image.name}: Configuring build...")

    available_element_sources: list[str] = [
        ELEMENTS_PATH,
        *(e.elements_path for e in THIRD_PARTY_ELEMENT_SOURCES),
    ]

    # Build environment to pass to elements
    env: dict[str, str] = {
        "DIB_CC_PROVENANCE": image.provenance,
        "ELEMENTS_PATH": ":".join(available_element_sources),
        "DIB_IMAGE_CACHE": image.cache_path,
        "DIB_DEBUG_TRACE": "1",
    }

    # add list of artifacts to environment?
    for a in image.artifacts:
        if a.name:
            env[a.name] = a.download_url


    os.environ.update(env)
    disk_format = "raw,qcow2"
    LOG.info(f"BUILD {image.name}: {pprint.pformat(env)}")
    args = [
        "disk-image-create",
        "-a",
        image.arch.value,
        "-o",
        image.base_path,
        "-t",
        disk_format,
        "--no-tmpfs",
        "--image-cache",
        image.cache_path,
        image.base_name.lower(),
    ]

    LOG.info(f"BUILD {image.name}: Waiting for an opportunity to execute build...")
    with semaphore:
        LOG.info(f"BUILD {image.name}: Building!")
        # We could technically call disk_image_create.main() right here,
        # but it just hard execs into a bash script, overwriting this process.
        # When that happens, the code after this point never runs.
        # Because of this, we have to run it as yet another subprocess.
        proc = subprocess.run(args, env=os.environ)
        if error := proc.returncode:
            LOG.error(
                "Error executing disk-image-create. "
                "Details should be present in log above.",
            )
            sys.exit(error)

        LOG.info(f"BUILD {image.name}: Build complete!")
        # Alert all dependents that their parent image has finished building
        with finished_building:
            finished_building.notify_all()
