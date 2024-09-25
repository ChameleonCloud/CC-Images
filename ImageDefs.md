# Properties of Chameleon Supported Images

Chameleon supported images are intended to be run the context of a Chameleon site,
either baremetal or virtualized. In order for users to have a consistent experience,
images must support the following:


| Image                  | Status                         |
| ---------------------- | ------------------------------ |
| cc-centos9-stream      | OK                             |
| cc-centos9-stream-cuda | Breaks when adding `cuda-12-6` |
| cc-ubuntu24.04         | OK                             |
| cc-ubuntu24.04-cuda    | OK                             |

## Partition layout and boot
The image must be bootable on both BIOS and UEFI-based systems. For this reason, we use
the diskimage-builder [block-device-efi](https://github.com/openstack/diskimage-builder/blob/master/diskimage_builder/elements/block-device-efi/block-device-default.yaml)
element, configured as:

- GPT (not MBR) partition table
- 550MiB "ESP" partition for `/boot/efi`
- 8MiB "BSP" partition, as a [bios boot partition](https://en.wikipedia.org/wiki/BIOS_boot_partition).
- The remaining disk space is a single partiton mounted to `/`, currently standardized on ext4 for ubuntu images, and XFS on centos images, to match upstream defaults.
    - Note: this is an area we could customize, for example introducing LVM or a snapshot aware filesystem, or other features.

## Image RootFS

At a minimum, images [must suport cloud-init](https://cloudinit.readthedocs.io/en/stable/reference/distros.html). The Distro default configuration is placed in `/etc/cloud/cloud.cfg`. As modifying this directly will require staying up-to-date with [per-distro-release changes](https://cloudinit.readthedocs.io/en/stable/explanation/configuration.html#distro-providers). For details, see the cloud-init [base configuration docs](https://cloudinit.readthedocs.io/en/stable/reference/base_config_reference.html).

Instead, we place additional configuration into `/etc/cloud/cloud.cfg.d`, overriding subsets of the vendor configuration. Additional scripts can be placed into `/var/lib/cloud/scripts/{per-boot,per-instance,per-once}`, but be aware that this has little control of when they execute in the boot process. Instead, it is preferred to create systemd units
or similar mechansims to control the order and dependencies of custom actions.

## Image Features

At a minimum, the following features are required for a consistent user experience.

### Default User Accounts
- `cc` user
    - The default user account must be named `cc`
    - Have uid/gid=`1000`
    - Have passwordless sudo via `ALL=(ALL) NOPASSWD:ALL`
    - have no password, and the use of a password disabled
    - have the default shell set to `bash`
- `ccadmin` user:
    - An additional user account must be created with name `ccadmin`
    - Have uid/gid=`1010`
    - Have passwordless sudo via `ALL=(ALL) NOPASSWD:ALL`
    - have no password, and the use of a password disabled
    - have the default shell set to `bash`
    - Have the following SSH public-key loaded (TODO: make this dynamic):

      ```
      ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDIP5yCb+pms83A9f0JPDx+ILOAYy7OoxPf5MjZlL+JW/bWRKuMmQDYLi6F22QoFlRrL0LsNsR8m28F/4uox81QOVq6D+uXODUe0FLJF1SLowxVrhvtEQSb0p2Ep3F3Isk6niEVTYNz+Uyx1s5jZ3xF1CjUFt8fhggkZEn+mAxux8FQO35mJF0mbEVNAA/ZiApLmM8/oBxtOd9T3QHEoXD5wensAWlGk2HdQVUMHNFRLZPl3Oo4BHYI3CbD/mu6dOZLOF/bvJF6dnwmQI+JflSLHLwGObKdi96w+sOEQfuYA1hMCes4M7rTkrNwAoLJUxZjr/l1/EgJJbbEIGiKOUW4TtNTiaIfV58ynhKdlvd7sIEquWGnPTtz3qviSkEmPiub48mt99sMXbHCNOFTz4dIwtjC2RQEWbRbccdVYRYBXXM9p5lThcRiyWrgkneIi/wfaRCKXzpzhSREgWWrFQ6/8p0ZbLeT/UGP6B0Lo7u1MsTSGa54VzK8AfhYJLMXJH/V+59g0iMN/owcUknI6KdLrsP9TW9jB7mKwtHBHyxC4IGcEKwwT+rW1hyz3JfHr0GEzt4FW86Ryyv2nb4yB4RC/R8YkWOM9mSJsQbZkAmXVWVJLCzE36cH0SgyFZvYfW2O7Ly+pwnVIgoPfowRTHCxCyO07qI+S22WLEH1HNw98w== Chameleon admin access
      ```

### Additional features for CC user account
The CC user account (TODO: Make this configurable), must also have the following configured:
1. Automatic login via the serial console:
    1. So that users can access their instances via the serial console, especially without networking, the CC user account must be set to have a getty with autologin.
    2. This is currently provided via a systemd unit that executes: `/sbin/agetty --keep-baud 115200,38400,9600 --autologin cc --noclear %I $TERM` on all accessed TTYs.
2. An openstack `openrc` file created at `/home/cc/openrc`, with values fetched from the chameleon vendordata service, implementing openstack's "dynamic vendordata" specification. This allows the `cc` user to authenticate to the site's API as the launching user, with some caveats. (see [private vendordata repo](https://github.com/ChameleonCloud/chameleon-vendordata))
3. `/home/cc/.ssh/authorized_keys` should be populated with:
    1. the ssh public key specified to nova at boot time (via user-data)
    2. all public keys attached to the user's openstack account (via vendordata)
        1. TODO: examine cloud-init's "public keys" feature, rather than our reimplementation.
4. At sites with an object store, the project's buckets should be `fuse` mounted to `/home/cc/my_mounting_point`

### CUDA images
Ensure that the following have been added:
- `pci=realloc=off` is added to the kernel commandline
- `nvidia-smi` works on a system with a GPU

### Additional image features

1. Time synchronization via NTP must work at all sites. To this end, we currently configure `chrony` with some extra ntp servers to work around firewalls blocking outbound public NTP access.
2. Firewalling: As baremetal sites do not have security groups, and as an extra layer of security for VM images, a host firewall is installed and active by default, with only SSH on port 22 allowed. (Currently `firewalld`)
3. SSH Hardening: ssh must be configured with:
    1. password login disabled
    2. root login disabled
    3. only key-based login enabled
    4. modern security standards applied as per [mozilla's guidelines](https://infosec.mozilla.org/guidelines/openssh)
4. cc-snapshot installed and functional

#### cc-snapshot details

This feature is more involved, as cc-snapshot is nuanced and slightly brittle.
At its core, the [cc-snapshot](https://github.com/ChameleonCloud/cc-snapshot/blob/master/cc-snapshot) script must be present, but the image must be configured such that it's usable.

This implies:
1. necessary dependencies are installed, primarily:
    1. `virt-sysprep`
    2. `qemu-img convert`
    3. `python-glanceclient`
2. Image provenance data is present on disk

CC-Snapshot will only back up a single root partition, and will then regenerate the necessary EFI and BIOS partitions, grub configuration, and so on, before creating a new glance disk image.

# Build Process
The contents of the rootfs must simply be bootable, but are currently provided via the following mechansim:
1. diskimage-builder element (e.g. `ubuntu`, `centos`) fetches an upstream cloud image rootfs.
2. additional elements (defined in this repo) apply changes on top of that rootfs, executed inside chroots. (see diskimage-builder build-stages).

This detail is noted as other mechanisms to obtain the same result (a bootable rootfs) are not ruled out, for example modifying a full image via something like `packer` or other image
ci/cd tools.
