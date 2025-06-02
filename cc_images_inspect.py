import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import requests
import yaml
from tqdm import tqdm


def load_config(path: Path):
    data = yaml.safe_load(path.read_text())
    return data.get('checks', {})


def mount(qcow_path: Path) -> Path:
    root_mount_dir = Path(tempfile.mkdtemp(prefix="guestmount_root_"))
    subprocess.check_call([
        'sudo',
        'env', 'LIBGUESTFS_BACKEND=direct',
        'guestmount',
        '-a', str(qcow_path),
        '-i',
        '--ro',
        str(root_mount_dir)
    ])

    user_mount_dir = Path(tempfile.mkdtemp(prefix="guestmount_user_"))
    subprocess.check_call([
        'sudo', 'bindfs',
        '-u', getpass.getuser(),
        '-g', getpass.getuser(),
        str(root_mount_dir),
        str(user_mount_dir)
    ])

    return root_mount_dir, user_mount_dir


def perform_checks(qcow_path: Path, mount_dir: Path, checks: dict):
    """Apply configured checks against the mounted filesystem."""
    for location, rules in checks.items():
        target = mount_dir / location
        for exe in rules:
            path = target / exe
            if not (path.exists() and os.access(path, os.X_OK)):
                raise RuntimeError(f"Missing executable {exe} in {location}")
    print(f"{qcow_path.name} passed all user-defined checks")


def cleanup(root_mount_dir: Path, user_mount_dir: Path):
    subprocess.check_call(['sudo', 'guestunmount', str(user_mount_dir)], shell=False)
    subprocess.check_call(['sudo', 'guestunmount', str(root_mount_dir)], shell=False)
    shutil.rmtree(str(user_mount_dir), ignore_errors=True)
    shutil.rmtree(str(root_mount_dir), ignore_errors=True)


def verify_manifest(qcow_path: Path, mount_dir: Path):
    """Verify DIB manifest against the image if running locally (only works on Ubuntu images)."""
    print(f"Verifying manifest for {qcow_path.name}...")
    manifest_path = qcow_path.parent / f"{qcow_path.stem}.d" / 'dib-manifests' / f"dib-manifest-dpkg-{qcow_path.stem}"

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        # only check the manifest against successfully installed packages
        pkgs = {p['package'].split(':')[0] for p in manifest.get('packages', []) if p.get('status') == 'ii '}
        status_file = mount_dir / 'var' / 'lib' / 'dpkg' / 'status'

        if not status_file.exists():
            print(f"dpkg status file missing, skipping manifest checks", file=sys.stderr)
        else:
            content = status_file.read_text().splitlines()

            installed_packages = set()
            current_package = None
            current_status = None

            for line in content:
                if line.startswith('Package: '):
                    if current_package and current_status == 'install ok installed':
                        installed_packages.add(current_package)
                    current_package = line.split(': ', 1)[1]
                    current_status = None

                if line.startswith('Status: ') and current_package:
                    current_status = line.split(': ', 1)[1]

            if current_package and current_status == 'install ok installed':
                installed_packages.add(current_package)

            missing = pkgs - installed_packages
            if missing:
                raise RuntimeError(f"Missing packages: {missing}")

            print(f"{qcow_path.name}: all {len(pkgs)} packages in manifest installed")
    else:
        print(f"WARNING: Manifest not found for {qcow_path.name}, skipping package checks")


def inspect_image(qcow_path: Path, checks: dict, is_local: bool = True):
    """Orchestrate the full inspection workflow for an image."""
    print(f"Inspecting {qcow_path.name}...")
    root_mount_dir, mount_dir = mount(qcow_path)
    try:
        perform_checks(qcow_path, mount_dir, checks)
        if is_local:
            verify_manifest(qcow_path, mount_dir)
        else:
            print(f"Skipping manifest verification for {qcow_path.name} as it's not a local build.")
    finally:
        cleanup(root_mount_dir, mount_dir)


def download_image(url: str, dest: Path, show_progress: bool = False):
    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    total = int(resp.headers.get('content-length', 0))
    with open(dest, 'wb') as f:
        if show_progress:
            bar = tqdm(total=total, unit='B', unit_scale=True, desc=dest.name)
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                if show_progress:
                    bar.update(len(chunk))
        if show_progress:
            bar.close()


def cmd_local(args):
    checks = load_config(Path(args.config))
    failed = []
    for p in args.paths:
        try:
            inspect_image(Path(p), checks, is_local=True)
        except Exception as e:
            print(f"ERROR inspecting {p}: {e}", file=sys.stderr)
            failed.append(p)
    return failed


def cmd_url(args):
    checks = load_config(Path(args.config))
    show_progress = args.show_progress
    current = json.loads(requests.get(f"{args.url}/current").text)
    names = args.images or list(current.keys())
    tmp = Path(tempfile.mkdtemp())
    failed = []
    try:
        for name in names:
            ver = current.get(name)
            if not ver:
                print(f"Warning: {name} missing in current.json", file=sys.stderr)
                failed.append(name)
                continue
            fname = f"{name}.qcow2"
            image_url = f"{args.url}/versions/{ver}/{fname}"
            print(f"Downloading {image_url}")
            out = tmp / fname
            download_image(image_url, out, show_progress)
            try:
                inspect_image(out, checks, is_local=False)
            except Exception as e:
                print(f"ERROR inspecting {name}: {e}", file=sys.stderr)
                failed.append(name)
    finally:
        shutil.rmtree(str(tmp))

    return failed


def main():
    rc = 0

    parser = argparse.ArgumentParser(prog='cc-images-inspect')
    parser.add_argument('--config', '-c', default='config/inspect.yaml', help='Path to inspection config file')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p1 = sub.add_parser('local', help='Inspect local qcow2 images')
    p1.add_argument('-p', '--paths', nargs='+', required=True, help='Paths to .qcow2 files')
    p1.set_defaults(func=cmd_local)

    p2 = sub.add_parser('url', help='Download and inspect images from URL')
    p2.add_argument('--url', '-u', required=True, help='Base container URL')
    p2.add_argument('-i', '--images', nargs='*', help='Specific image names to inspect')
    p2.add_argument('--show-progress', action='store_true', help='Show download progress bar')
    p2.set_defaults(func=cmd_url)

    args = parser.parse_args()
    failed = args.func(args)
    if failed:
        print(
            f"Inspection failed for {len(failed)} image(s): {failed}",
            file=sys.stderr
        )
        rc = 1
    else:
        print("Inspection passed all checks for all images!", file=sys.stdout)

    return rc


if __name__ == '__main__':
    sys.exit(main())
