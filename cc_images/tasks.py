"""
Defines concurrency and order for how builds/pushes will be deployed
"""
import logging
import multiprocessing
import os
import shutil
import sys
import time
from collections import defaultdict

from cc_images import process_context, process_manager
from cc_images.args import CCImagesArgs
from cc_images.build import do_build
from cc_images.image import ChameleonImage
from cc_images.push import do_push
from cc_images.sites import get_sites
from cc_images.third_party import ensure_third_party_elements

LOG = logging.getLogger(__name__)


def _killall(proclist: "list[multiprocessing.Process]"):
    for proc in proclist:
        proc.kill()

def run_tasks(cmdline: CCImagesArgs, images_to_run: "list[ChameleonImage]"):
    """
    Defines what tasks cc-images has to run, and queues them asynchronously
    """
    ensure_third_party_elements()
    LOG.info("Defining tasks to execute...")

    # Each task must acquire this semaphore, which ensures that we do not go above the configured
    # limit of concurrent tasks
    semaphore = process_manager.Semaphore(value=cmdline.n_tasks)
    # Alerts dependent builds and pushes that a build has finished
    is_built = defaultdict(process_manager.Condition)
    tasks: list[multiprocessing.Process] = []

    for image in images_to_run:
        will_build = cmdline.do_build
        if cmdline.destroy_cache:
            LOG.warning("Destroying cache, as requested by -f")
            will_build = True
            shutil.rmtree(image.cache_path, ignore_errors=True)
            shutil.rmtree(image.raw_path, ignore_errors=True)
            shutil.rmtree(image.qcow_path, ignore_errors=True)

        if cmdline.do_push and not image.local_build_exists():
            # If the user has requested to push an image which doesn't exist,
            # we have to build first
            will_build = True
            LOG.warning(
                f"{image.name} does not have a local copy to push. Building first."
            )

        if will_build:
            deps = [p for p in image.parents if p.should_build_with(cmdline)]
            LOG.debug(f"Image {image.name} will wait on {[i.name for i in deps]}.")
            tasks.append(
                process_context.Process(
                    target=do_build,
                    args=(
                        image,
                        [is_built[d] for d in deps],
                        semaphore,
                        is_built[image],
                    ),
                    name=f"BUILD-{image.name}",
                )
            )

        if cmdline.do_push:
            for site in get_sites():
                if not site.is_baremetal and image.baremetal_only:
                    continue
                tasks.append(
                    process_context.Process(
                        target=do_push,
                        args=(image, site, will_build, cmdline.scope, cmdline.version, semaphore, is_built[image]),
                        name=f"PUSH-{image.name}-{site.name}",
                    )
                )

    LOG.info(f"Queued {len(tasks)} tasks! ({cmdline.n_tasks} max concurrent)")
    for proc in tasks:
        proc.start()
    while True:
        alive = [t for t in tasks if t.is_alive()]
        not_alive = [t for t in tasks if not t.is_alive()]
        print(f"Parent: Waiting on {len(alive)} tasks...")
        for proc in alive:
            print(f"WAIT: {proc.name}")
        for proc in not_alive:
            if proc.exitcode != os.EX_OK:
                LOG.info("Got bad return from task. Terminating...")
                _killall(alive + not_alive)
                sys.exit(proc.exitcode)
        if not alive:
            _killall(not_alive)
            return
        else:
            time.sleep(30)
