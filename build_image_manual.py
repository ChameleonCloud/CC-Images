import subprocess
import yaml
from time import perf_counter
from pathlib import Path
import logging
from dataclasses import dataclass, field
from collections.abc import Mapping

from concurrent.futures import ThreadPoolExecutor, as_completed


class ImageBuildException(BaseException):
    pass


def build_an_image(image_name, arch, elements, envs):
    build_path = Path("/opt/scratch/cc-images/build")

    cache_path = build_path.joinpath("cache",image_name)
    #ensure cache_path exists
    cache_path.mkdir(parents=True, exist_ok=True)

    image_build_dir = build_path.joinpath("images")
    #ensure image_build_dir exists
    image_build_dir.mkdir(parents=True, exist_ok=True)

    image_name_path = image_build_dir.joinpath(image_name).as_posix()
    logfile = image_build_dir.joinpath(f"{image_name}.log")
    logfile.unlink(missing_ok=True)

    elements_path = Path.cwd().joinpath("elements")

    args = []
    args.extend(["-a", arch])
    args.extend(["-o", image_name_path])
    args.extend(["--logfile", logfile.as_posix()])
    args.extend(["-t", "raw,qcow2"])
    args.extend(["--qemu-img-options", "compression_type=zstd"])

    args.extend(elements)

    env = {
        "DIB_IMAGE_CACHE": cache_path,
        "ELEMENTS_PATH": elements_path.as_posix(),
    }
    env.update(envs)

    logging.info(f"starting build for {image_name}")

    build_start_time_s = perf_counter()
    try:
        result = subprocess.run(
            shell=True,
            capture_output=True,
            check=True,
            executable=".venv/bin/disk-image-create",
            args=args,
            env=env,
        )
    except subprocess.CalledProcessError as ex:
        raise ImageBuildException(ex.stderr)
    else:
        build_end_time_s = perf_counter()
        elapsed_time_s = build_end_time_s - build_start_time_s
        logging.info(f"Completed build for {image_name} in {elapsed_time_s} seconds")
        return {"returncode": result.returncode, "duration": elapsed_time_s}



def load_images_to_build(yaml_path):
    with open("images_to_build.yaml") as f:
        image_defs = yaml.safe_load(f)

    images_to_build={}
    for key, values in image_defs.items():
        if str.startswith(key, "x-"):
            """skip template only entries"""
            continue



        elements = set(values.get("elements"))
        extra_elements = set(values.get("extra_elements", []))
        elements.update(extra_elements)


        images_to_build[key]={
            "arch": values.get("arch"),
            "elements": list(elements),
            "envs": values.get("envs")
        }

    return images_to_build




def main():
    logging.basicConfig(level=logging.DEBUG)

    images_to_build = load_images_to_build("images_to_build.yaml")


    with ThreadPoolExecutor(max_workers=10) as executor:
        tasks = {}
        for name, values in images_to_build.items():
            if not name == "cc-rocky-9":
                continue

            kwargs = {
                "image_name": name,
                "arch": values.get("arch"),
                "elements": values.get("elements"),
                "envs": values.get("envs"),
            }
            future = executor.submit(build_an_image, **kwargs)
            tasks[future] = kwargs

        logging.info('Waiting for tasks to complete')

        for future in as_completed(tasks):
            args = tasks[future]
            image_name = args.get("image_name")
            try:
                result = future.result()
            except ImageBuildException as ex:
                logging.warning(f"{image_name} did not build successfully, with error {ex}")


if __name__ == "__main__":
    main()
