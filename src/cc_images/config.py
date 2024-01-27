import enum
import logging
import os
import sys
from typing import Union
import yaml

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
LOG = logging.getLogger(__name__)

_cc_images_path = os.path.dirname(__file__)
ELEMENTS_PATH = os.path.abspath(os.path.join(_cc_images_path, "..", "elements"))
os.environ.setdefault("ELEMENTS_PATH", ELEMENTS_PATH)

IMAGE_CONFIG_PATH = os.getenv(
    "CC_IMAGES_CONFIG", os.path.join(_cc_images_path, "images.yaml")
)

BUILD_PATH = os.path.abspath(os.path.join(_cc_images_path, "..", "build"))
if not os.path.exists(BUILD_PATH):
    os.mkdir(BUILD_PATH)

IMAGE_OUTPUT_PATH = os.path.join(BUILD_PATH, "images")
if not os.path.exists(IMAGE_OUTPUT_PATH):
    os.mkdir(IMAGE_OUTPUT_PATH)

IMAGE_CACHE_PATH = os.path.join(BUILD_PATH, "cache")
if not os.path.exists(IMAGE_CACHE_PATH):
    os.mkdir(IMAGE_CACHE_PATH)


def _read_images_yaml() -> "dict[str, Union[dict, str, int, list, None]]":
    with open(IMAGE_CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def get_supported_image_names() -> "list[str]":
    image_config = _read_images_yaml()
    return list(sorted(img.lower() for img in image_config.keys()))


class Architecture(enum.Enum):
    AMD64 = "amd64"
    ARM64 = "arm64"
