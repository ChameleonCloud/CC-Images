# CC-Images

This is a tool used to configure, build, and push images for Chameleon.
It is easy to extend, and takes heavy advantage of build hosts with lots of compute resources.

## Installation

The project uses a virtualenv and has some dependency requirements, to set it up:
1. `python -m venv .venv`: create the virtualenv
2. `. .venv/bin/activate`: to activate the virtualenv
3. `pip install .`: to install dependencies of the project

Note: Using system python packages can result in broken images. It's highly recommended to use a virtualenv.

On the system you'll need the following additional packages:

```
apt-get install \
  python3 \
  python3-dev \
  python3-venv \
  qemu-utils \
  qemu-user \
  qemu-user-binfmt \
  git \
  gcc \
  cpio \
  xz-utils  \
  dosfstools \
  zstd
```

Note: If you're building baremetal images, then `qemu-img` must be installed on the build host.

## Usage

```
usage: cc-images.py [-h] [-b] [-p] [-f] [-t N_TASKS] [-a [amd64,arm64]]
                    {cc-centos7,cc-centos7-cuda,cc-centos7-nallatech,cc-centos7-terasic,cc-centos7-xilinx,cc-centos8-stream,cc-centos8-stream-cuda,cc-centos9-stream,cc-centos9-stream-cuda,cc-ubuntu20.04,cc-ubuntu20.04-cuda,cc-ubuntu22.04,cc-ubuntu22.04-cuda}
                    [{cc-centos7,cc-centos7-cuda,cc-centos7-nallatech,cc-centos7-terasic,cc-centos7-xilinx,cc-centos8-stream,cc-centos8-stream-cuda,cc-centos9-stream,cc-centos9-stream-cuda,cc-ubuntu20.04,cc-ubuntu20.04-cuda,cc-ubuntu22.04,cc-ubuntu22.04-cuda} ...]

Chameleon official image building/publishing tool, based on OpenStack's
diskimage-builder

positional arguments:
  {cc-centos7,cc-centos7-cuda,cc-centos7-nallatech,cc-centos7-terasic,cc-centos7-xilinx,cc-centos8-stream,cc-centos8-stream-cuda,cc-centos9-stream,cc-centos9-stream-cuda,cc-ubuntu20.04,cc-ubuntu20.04-cuda,cc-ubuntu22.04,cc-ubuntu22.04-cuda}
                        The image tag(s) to build

options:
  -h, --help            show this help message and exit
  -b, --build           Build new versions of the listed image tags
  -p, --push            Push the most recent version of the image(s) in the
                        cache. When combined with -b, pushes the image(s) just
                        built.
  -f, --force           Force a complete rebuild of the image(s) without
                        reusing the cache. Destroys the cache for the image(s)
                        in the process.
  -t N_TASKS, --tasks N_TASKS
                        The number of build tasks to run in parallel, where
                        applicable. By default, only one task is run at a
                        time, as it can get very resource-intensive
  -a [amd64,arm64], --architecture [amd64,arm64]
                        Comma-separated list of architectures to build/push.
                        Uses all supported architectures for each image by
                        default.
```

## Configuration

Default config (YAML) files are located directly in the [`cc_images`](cc_images) package. Different
files can be used by setting several environment variables:

* `CC_IMAGES_CONFIG`: Overrides [images.yaml](cc_images/images.yaml)
* `CC_SITES_CONFIG`: Overrides [sites.yaml](cc_images/sites.yaml)
* `CC_THIRD_PARTY_ELEMENTS_CONFIG`: Overrides [third-party.yaml](cc_images/third-party.yaml)

## Building

Building is triggered by the `-b/--build` flag. When a build is triggered, `cc-images` evaluates
which images should be built at start time. It will build whichever images requested
by the positional arguments, and may also build additional images if it improves cache efficiency
for the requested images.

Any images which don't depend on each other will be built in parallel if the number specified
by `-t`
is greater than 1. These dependencies (and other configurations) are decided
by [images.yaml](cc_images/images.yaml), not the element hierarchy.

### Artifacts

Some images may rely on remote files which are not easily downloadable from their source locations
(For example, a tarball which requires one to accept an EULA on a webpage before downloading). These
files can be uploaded to an object store, and then defined as `artifacts`
in [images.yaml](cc_images/images.yaml). Artifacts defined there will be automatically downloaded
and emplaced within the build cache for appropriate images. It is up to the elements which require
these artifacts to implement how they are used beyond that.

### Caching

`cc-images` caches very aggressively and does not delete images after they've been pushed. Be warned
that it will eat up a lot of disk space if many different images are built without clearing the
cache.

### Building ARM on x86-based Architectures

You can use qemu emulation to build ARM images on x86 systems, however, it is significantly
slower. If you still wish to do so (or don't have access to an arm system) make sure to
install the qemu static binaries for arm emulation:
```
sudo apt install qemu-user-static binfmt-support
```

And then configure it:
```
sudo update-binfmts --enable qemu-aarch64
```

After that you should be able to build the arm images using `cc-images.py` specifying
`arm64` as the architecture.

However, on a system that takes around 5-7 minutes to build an x86 version of the Ubuntu24.04
image, it took about 2 hours and 5 minutes to build the arm image using qemu emulation:
```
INFO:cc_images.build:BUILD CC-Ubuntu24.04-ARM64: Build complete!
Parent: Waiting on 0 tasks...
INFO:__main__:Finished in 2:05:38.122256
```

Therefore, we strongly recommend you build arm images on arm systems rather than rely on
qemu emulation.

To disable arm binaries and revert back to the native x86 binaries you can run:
```
sudo update-binfmts --disable qemu-aarch64
```

## Pushing

NOTE: Before pushing images to a container for staging or production we *HIGHLY* recommend running
the [cc-images-inspect](#cc-images-inspect) tool on the images first. Assuming all of the
checks pass, you can push the images.

Push tasks are triggered by the `-p/--push` flag. When a push is triggered, it is queued
asynchronously just like builds. If a push is done alongside a build, or the requested image does
not exist in the cache, the push will wait for its image to be built before executing.

When images are pushed, they are transferred to a container in the object store.
The container structure in the object store is:
```
<base container name>/<scope>/versions/<date>-<version>
```

The base container name is fixed and should be created manually ahead of time. The
default is `chameleon-supported-images`. The scope supports different images for production, staging,
and development. The initial implementation should only use `prod` for the scope. Future
iterations may add support for additional environments. The datetime is generated
automatically when the image is pushed.

When images are pushed, a new file called `current` is created in the scope level of the
container. This file contains the latest date-version that should be used for each image.

For example:
```
chameleon-supported-images/
chameleon-supported-images/prod/
chameleon-supported-images/prod/current
chameleon-supported-images/prod/versions/20250304-v2
chameleon-supported-images/prod/versions/20250304-v2/CC-Ubuntu24.04.manifest
chameleon-supported-images/prod/versions/20250304-v2/CC-Ubuntu24.04.qcow2
chameleon-supported-images/prod/versions/20250304-v1
chameleon-supported-images/prod/versions/20250304-v1/CC-Ubuntu24.04.manifest
chameleon-supported-images/prod/versions/20250304-v1/CC-Ubuntu24.04.qcow2
chameleon-supported-images/prod/versions/20250304-v1/CC-Ubuntu22.04.manifest
chameleon-supported-images/prod/versions/20250304-v1/CC-Ubuntu22.04.qcow2
chameleon-supported-images/prod/versions/20250303-v1
chameleon-supported-images/prod/versions/20250303-v1/CC-Ubuntu24.04.manifest
chameleon-supported-images/prod/versions/20250303-v1/CC-Ubuntu24.04.qcow2
chameleon-supported-images/prod/versions/20250303-v1/CC-Ubuntu22.04.manifest
chameleon-supported-images/prod/versions/20250303-v1/CC-Ubuntu22.04.qcow2
```

In this case the contents of the `current` file would be:
```
{
  "CC-Ubuntu24.04": "20250304-v2",
  "CC-Ubuntu22.04": "20250304-v1"
}
```

### Authentication

`cc-images` is configured as an OpenStack client
using [clouds.yaml](https://docs.openstack.org/python-openstackclient/latest/configuration/index.html#clouds-yaml)
in a standard location. For testing, it is recommended to simply use your personal OpenStack account
on a dev site so that official images are not overwritten. If you need to test on a prod site, using
your personal account on a non-admin project should be safe since official images are uploaded by
admins under the `openstack` project.

## Elements

Custom [elements](elements) are bundled into this repo for convenience. Elements are built as close
to [OpenStack's guidelines](https://docs.openstack.org/diskimage-builder/latest/developer/developing_elements.html)
as possible.

### Extending

It's very simple to create a new image/element within `cc-images`. The element should simply be
defined under the [elements](elements) directory, adhering as closely as possible
to [OpenStack's guidelines](https://docs.openstack.org/diskimage-builder/latest/developer/developing_elements.html)
. The element can take dependencies on any elements already included in the [elements](elements)
directory, elements defined by default
in [`diskimage-builder`](https://github.com/openstack/diskimage-builder/tree/master/diskimage_builder/elements)
, or imported [third-party elements](#third-party-elements).

If the new element describes an image, the image must also be defined
in [images.yaml](cc_images/images.yaml) in order for `cc-images` to build it.

New images built for Chameleon should always take a dependency on _at least_
the [cc-common](elements/cc-common) element.

**NOTE: ANY IMAGES BUILT BY THIS TOOL SHOULD NOT NECESSARILY BE EXPECTED TO WORK ANYWHERE EXCEPT
CHAMELEON.**

#### Third Party Elements

Third-party elements should simply be defined in [third-party.yaml](cc_images/third-party.yaml). Any
elements defined here will be automatically pulled and imported every time `cc-images` is run.

## Known Issues

* Currently, CentOS images need to be built on a CentOS host
* CentOS CUDA images are non-functioning
  * The Nvidia drivers are not loaded by the system
* The FPGA elements are untested and incomplete
  * Work on these will continue on more-modern stable operating system then CentOS7

## cc-images-inspect

A CLI for validating qcow2 images against configurable checks and the DIB manifest.

### Configuration

The cc-images-inspect tool is configured via a YAML file, typically named
`config/inspect.yaml`. This file defines a set of required files or executables that must be
present in specific locations within the mounted image filesystem.

Each key under checks is a relative filesystem path (e.g., usr/local/bin), from the root /.
The value should be a list of required executables in that directory.

Any missing executable in any image causes the image to be marked as failed.

### dib-manifest verification

If the script is running on images built locally it will compare the dib-manifest file of
the image with the contents of the image. The manifest file is expected to be in the following
location relative to the location of the image:
```
{image_name}.qcow2
{image_name}.d/dib-manifests/dib-manifest-dpkg-{image_name}
```

If the inspection is not run on local builds of an image, or the manifest file cannot be
found, it will print a note that manifest checking will be skipped.

*NOTE:* Checking the manifest against installed packages is not supported for CentOS images.

### Installation

Additional Ubuntu system packages for cc-images-inspect:
```bash
apt-get install libguestfs-tools bindfs
```

On CentOS you'll need the same packages:
```bash
dnf install libguestfs-tools bindfs
```

```bash
pip install .
```

### Usage

Inspect local qcow2 files:
```bash
cc-images-inspect local --paths path/to/image1.qcow2 path/to/image2.qcow2
```

Inspect specific remote images:
```bash
cc-images-inspect url \
  --url https://<your-bucket>/prod \
  --images CC-Ubuntu22.04 CC-CentOS9-Stream
```

Inspect all remote images:
```bash
cc-images-inspect url --url https://<your-bucket>/prod
```
