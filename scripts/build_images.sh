#!/bin/bash

set -euo pipefail

datestamp="$(date --iso-8601)"

# .venv/bin/python3 cc-images.py \
#     -t 10 \
#     -a amd64 \
#     -b \
#     cc-ubuntu20.04 \
#     cc-ubuntu22.04 \
#     cc-ubuntu20.04-cuda \
#     cc-ubuntu22.04-cuda \
#     2>"logs/${datestamp}-error.log" 1>"logs/${datestamp}-output.log"


DIB_RELEASE=jammy

ELEMENTS_PATH=./elements \
DIB_RELEASE=jammy \
.venv/bin/disk-image-create \
    -a amd64 \
    -t raw \
    -o "build/images/${DIB_RELEASE}-${datestamp}.raw" \
    cc-ubuntu22.04 \
&& qemu-img convert \
    -f raw -O qcow2 \
    -p \
    -c -o compression_type=zstd \
    "build/images/${DIB_RELEASE}-${datestamp}.raw" \
    "build/images/${DIB_RELEASE}-${datestamp}.qcow2"
