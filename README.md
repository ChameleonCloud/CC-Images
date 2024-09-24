# CC-Images

This is a tool used to configure, build, and push images for Chameleon.
It is easy to extend, and takes heavy advantage of build hosts with lots of compute resources.

## Installation

`cc-images` relies on a few third-party dependencies. It is recommended to create a virtualenv using
`poetry install` and `poetry env`. If you're building baremetal images, then `qemu-img` must be
installed on the build host.

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
by `-t` is greater than 1. These dependencies (and other configurations) are decided
by [images.yaml](cc_images/images.yaml), not the element hierarchy.

`ARCH=arm64` can be used to build arm images on x86_64 systems using qemu.

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

## Pushing

Push tasks are triggered by the `-p/--push` flag. When a push is triggered, it is queued
asynchronously just like builds. If a push is done alongside a build, or the requested image does
not exist in the cache, the push will wait for its image to be built before executing.

When an image is pushed, `cc-images` first seeks out an existing image under the configured
account (see [auth](#authentication)) with the same name as the to-be-pushed image. The old image is
archived by having its name appended with a timestamp. The new image assumes the former name of the
old image. If uploading the new image fails, the name change for the old image is rolled back.

If an image only functions on baremetal sites, then it will only be pushed to baremetal sites (
configured by [images.yaml](cc_images/images.yaml) and [sites.yaml](cc_images/sites.yaml)).

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

* CentOS7 images are non-functioning
    * There is an issue with the `grub` configuration for UEFI which prevents them from booting
    * There is an issue with autologin for non-UEFI nodes which prevents them from logging in
      post-boot
* CentOS CUDA images are non-functioning
  * The Nvidia drivers are not loaded by the system
* The FPGA elements are untested and incomplete
  * Work on these will continue on more-modern stable operating system then CentOS7