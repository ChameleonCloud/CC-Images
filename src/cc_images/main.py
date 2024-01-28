#! python3

import subprocess
import sys
import os.path
import sys
import diskimage_builder.paths




def run_disk_image_create(elements, environ={}):
    "Copy from disk_image_create, but override so we can control environment."

    # pre-seed some paths for the shell script
    environ['_LIB'] = diskimage_builder.paths.get_path('lib')

    # export the path to the current python
    if not environ.get('DIB_PYTHON_EXEC'):
        environ['DIB_PYTHON_EXEC'] = sys.executable

    # we have to handle being called as "disk-image-create" or
    # "ramdisk-image-create".  ramdisk-image-create is just a symlink
    # to disk-image-create
    # XXX: we could simplify things by removing the symlink, and
    # just setting IS_RAMDISK in environ here depending on sys.argv[1]
    script = "%s/%s" % (diskimage_builder.paths.get_path('lib'),
                        "disk-image-create")


    # prefix list of elements with the builder script
    args = [script]
    args.extend(elements)

    image_build_process = subprocess.run(
        executable=script,
        args=elements,
        env=environ
    )

cc_ubuntu_2004 = {
    "elements": [
        "vm",
        "block-device-efi",
        "ubuntu"
    ],
    "envs": {
        "ARCH": "amd64",
        "DIB_RELEASE": "focal"
    }
}


def main():

    images = []
    images.append(cc_ubuntu_2004)

    for image in images:
        elements = image.get("elements")
        envs = image.get("envs")
        builder = run_disk_image_create(elements, envs)

if __name__ == "__main__":
    main()
