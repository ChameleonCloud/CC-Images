#!/bin/bash

image_file="${1}"

qemu-system-x86_64 \
    -nographic \
    -enable-kvm \
    -cpu host \
    -smp 4 \
    -m 4096 \
    -drive "file=${image_file},snapshot=on,cache=none,if=virtio"
