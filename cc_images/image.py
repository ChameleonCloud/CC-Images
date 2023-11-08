import base64
import json
import logging
import os.path
from datetime import datetime
from functools import cached_property
from typing import Any, Union

import git

from cc_images.args import CCImagesArgs
from cc_images.artifacts import BuildArtifact
from cc_images.config import (IMAGE_CACHE_PATH, IMAGE_OUTPUT_PATH,
                              Architecture, _read_images_yaml)

LOG = logging.getLogger(__name__)


def _resolve_image_name(base_name: str, arch: Architecture) -> str:
    if arch == Architecture.AMD64:
        return base_name
    else:
        return f"{base_name}-{arch.name}"


class ChameleonImage:
    """
    Resolves the order in which images should be built. This order is represented as a tree, which
    will be traversed in such a way that no two elements that depend on each other will be built in
    parallel. For example, if the tree looks as such:

        A
        |
     B----C
     |    |
     D    E

     First, 'A' would be built. 'B' and 'C' depend on 'A', so they will wait.
     Then, 'B' and 'C' can be built in parallel.
     'D' will wait upon 'B' to finish. 'E' will wait upon 'C' to finish.
     Suppose 'B' finishes before 'C'. Then, 'D' will begin building in parallel with 'C'.
     Once 'C' finishes, then 'E' will begin building in parallel with 'D'

     The purpose of this class is to use the cache efficiently while still allowing for parallelism.

     ``parents`` describes the images upon which this image is cache-dependent. Its parents must
     be built before it can start building.
     ``children`` describes the images which are cache-dependent upon this image.
     ``arch`` describes the architecture this image will build with
     ```baremetal_only`` means this image should only be built for baremetal sites
     ``distro``, ``distro_release``, and ``variant`` are for provenance
    """

    def __init__(
        self,
        base_name: str,
        parents: "list[ChameleonImage]",
        arch: Architecture,
        baremetal_only: bool,
        distro: Union[str,None],
        distro_release:Union[str,None],
        variant: Union[str,None],
        artifacts: "list[BuildArtifact]",
    ):
        self.base_name = base_name
        self.parents: list[ChameleonImage] = parents or []
        for parent in self.parents:
            parent.add_child(self)
        self.children: list[ChameleonImage] = []
        self.arch = arch
        self.baremetal_only = baremetal_only or arch != Architecture.AMD64
        if distro:
            self.distro = str(distro)
        else:
            self.distro = self.parents[0].distro
        if distro_release:
            self.distro_release = str(distro_release)
        else:
            self.distro_release = self.parents[0].distro_release
        if variant:
            self.variant = str(variant)
        else:
            self.variant = self.parents[0].variant
        self.artifacts = artifacts

    def __eq__(self, other) -> bool:
        if isinstance(other, ChameleonImage):
            return self.base_name == other.base_name
        return self.base_name == other

    def __repr__(self) -> str:
        return self.name

    def __hash__(self) -> int:
        return hash(self.name)

    def add_child(self, child: "ChameleonImage") -> None:
        self.children.append(child)

    @property
    def build_repo(self) -> str:
        """build-repo metadata"""
        return "https://github.com/ChameleonCloud/cc-images"

    @cached_property
    def build_repo_commit(self) -> str:
        """build-repo-commit metadata"""
        repo = git.Repo(os.path.dirname(__file__), search_parent_directories=True)
        return repo.head.commit.hexsha

    @cached_property
    def build_timestamp(self) -> str:
        """build-timestamp metadata"""
        return str(datetime.utcnow())

    @cached_property
    def build_tag(self) -> str:
        """build-tag metadata"""
        return f"{self.name}-{self.build_timestamp}"

    @property
    def metadata(self) -> "dict[str, Any]":
        return {
            "build-distro": self.distro,
            "build-release": self.distro_release,
            "build-variant": self.variant,
            "build-repo": self.build_repo,
            "build-repo-commit": self.build_repo_commit,
            "build-timestamp": self.build_timestamp,
            "build-tag": self.build_tag,
            "build-ipa": "false",
        }

    @property
    def provenance(self) -> str:
        """
        Returns this image's metadata encoded as base64
        """
        return str(base64.b64encode(json.dumps(self.metadata).encode("utf-8")), "utf-8")

    @property
    def name(self) -> str:
        return _resolve_image_name(self.base_name, self.arch)

    @property
    def cache_path(self) -> str:
        if not self.parents:
            return os.path.join(IMAGE_CACHE_PATH, self.base_name)
        else:
            # This might cause issues in the future if we have a more complex image hierarchy
            return self.parents[0].cache_path

    @property
    def base_path(self) -> str:
        return os.path.join(IMAGE_OUTPUT_PATH, self.name)

    @property
    def raw_path(self) -> str:
        return f"{self.base_path}.raw"

    @property
    def qcow_path(self) -> str:
        return f"{self.base_path}.qcow2"

    def local_build_exists(self) -> bool:
        qcow_exists = os.path.exists(self.qcow_path)
        if self.baremetal_only:
            return qcow_exists
        else:
            return qcow_exists and os.path.exists(self.raw_path)

    def has_child(self, child) -> bool:
        return child in self.children or any(c.has_child(child) for c in self.children)

    def should_build_with(self, cmdline: CCImagesArgs) -> bool:
        """
        Determines if this image should be built directly based on the command-line arguments
        """
        if self.arch not in cmdline.arch:
            return False
        # If the user has explicitly requested this image to be built, then build it
        if self.base_name.lower() in cmdline.images:
            return True

        n_children_building = sum(self.has_child(img) for img in cmdline.images)
        # If we're building 2 or more of this image's children, then we will see performance
        # improvements by building this image first. This is because the children will both be
        # able to share the cache generated by building this image rather than clobbering
        # the cache at the same time while building concurrently
        if n_children_building >= 2:
            return True

        return False


def resolve_image_hierarchy(cmdline: CCImagesArgs) -> "list[ChameleonImage]":
    """
    Loads images.yaml and builds a hierarchy of all the supported images.
    Returns a list of all images that will be built
    """
    image_defs = _read_images_yaml()

    name_map: dict[str, ChameleonImage] = {}
    root_images: list[ChameleonImage] = []

    def define_image(name: str) -> None:
        """
        Recursively converts YAML definitions of images into ``ChameleonImage`` objects
        """
        if name in name_map:
            # If the image has already been defined, continue
            return

        # Grab any additional configuration about the image from the YAML file
        image_config = image_defs[name]
        if not image_config:
            image_config = {}

        arches = [
            Architecture(a) for a in image_config.get("arch", [Architecture.AMD64])
        ]
        baremetal_only = image_config.get("baremetal-only", False)
        for arch in arches:
            # Define one image for each supported architecture
            parent_names = image_config.get("depends", [])
            parents = []
            for p in parent_names:
                full_name = _resolve_image_name(p, arch)
                if full_name not in name_map:
                    # Recursive case: if parent images haven't been defined yet, define them first
                    define_image(p)
                parents.append(name_map[full_name])

            provenance = image_config.get("provenance", {})
            artifacts = image_config.get("artifacts", {})
            # Base case: creates a ChameleonImage object
            new_image = ChameleonImage(
                name,
                parents,
                arch,
                baremetal_only,
                provenance.get("distro"),
                provenance.get("release"),
                provenance.get("variant"),
                [
                    BuildArtifact(a := artifacts[name], a["object"], a["site"])
                    for name in artifacts
                ],
            )
            name_map[new_image.name] = new_image
            if not new_image.parents:
                root_images.append(new_image)

    for image_name in image_defs:
        define_image(image_name)

    LOG.info("Resolved image config")
    LOG.info("Determining which images should be built for max efficiency")

    def get_images_to_build(images_in: "list[ChameleonImage]") -> "list[ChameleonImage]":
        """
        Iterates over images and creates a list of all the images that should be built directly.
        See ChameleonImages.should_build_with for more context
        """
        approved: list[ChameleonImage] = []
        for img in images_in:
            if img.should_build_with(cmdline):
                approved.append(img)
            approved += get_images_to_build(img.children)
        return approved

    return get_images_to_build(root_images)
