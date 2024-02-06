#!/bin/bash

set -euo pipefail
set -x

image_name_base="cc-ipa"

#distro="centos"
#release="9-stream"

distro="debian-minimal"
release="bookworm"

openstack_branch="stable/2023.1"
# openstack_branch="stable/xena"

# arch="amd64"
arch="arm64"

branch_shortname="$(echo ${openstack_branch} | cut -d "/" -f 2)"
image_name_full="${image_name_base}-${branch_shortname}-${distro}-${release}-${arch}"
image_name_cache="${image_name_base}-${distro}-${release}"
echo "${image_name_full}"
image_output_base="/opt/scratch/cc-images/build/images"
image_cache_base="/opt/scratch/cc-images/build/cache"

DIB_IMAGE_CACHE="${image_cache_base}/${image_name_cache}" \
    ironic-python-agent-builder \
    --lzma \
    -b "${openstack_branch}" \
    --extra-args "-a ${arch}" \
    -o "${image_output_base}/${image_name_full}" \
    -r "${release}" "${distro}"
