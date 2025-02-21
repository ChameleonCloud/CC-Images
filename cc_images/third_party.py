import logging
import os
import shutil

import git
import yaml
from urllib3.util import Url, parse_url

from cc_images.config import BUILD_PATH

LOG = logging.getLogger(__name__)
THIRD_PARTY_PATH = os.path.join(BUILD_PATH, "third-party")
if not os.path.exists(THIRD_PARTY_PATH):
    os.mkdir(THIRD_PARTY_PATH)


class ElementSource:
    """
    Describes minimal required information about a third-party element source
    """

    def __init__(self, name: str, remote: Url, branch: str, elements_dir: str) -> None:
        self.name = name
        self.branch = branch
        self.remote = remote
        self.elements_dir = elements_dir
        if not os.path.exists(self.path):
            self.clone()
        else:
            self.pull()

    def clone(self):
        LOG.info(f"Cloning element source {self.name}...")
        git.Repo.clone_from(
            self.remote.url,
            self.path,
            b=self.branch,
        )

    def pull(self):
        LOG.info(f"Updating element source {self.name}...")
        repo = git.Repo(self.path)
        if repo.remotes.origin.url.lower() != self.remote.url.lower():
            LOG.warning(f"Upstream for element source {self.name} changed!")
            shutil.rmtree(self.path)
            return self.clone()
        repo.git.checkout(self.branch)
        repo.remotes.origin.pull(self.branch)

    @property
    def path(self):
        """
        Describes the root path of the cloned repository.
        For the path to the elements, see ``elements_path``
        """
        return os.path.join(THIRD_PARTY_PATH, self.name)

    @property
    def elements_path(self):
        """
        Describes the path to the elements within the source repo
        """
        return os.path.join(self.path, self.elements_dir)


THIRD_PARTY_ELEMENT_SOURCES: "list[ElementSource]" = []


def ensure_third_party_elements():
    """
    Ensures third-party elements are downloaded and up-to-date
    """
    global THIRD_PARTY_ELEMENT_SOURCES
    application_path = os.path.join(os.path.dirname(__file__), "..")
    default_third_party_path = os.path.join(application_path, "config",
                                            "third-party.yaml")
    third_party_path = os.getenv(
        "CC_THIRD_PARTY_ELEMENTS_CONFIG",
        default_third_party_path,
    )
    with open(third_party_path, "r") as f:
        element_config = yaml.safe_load(f)

    for element in element_config:
        element_info = element_config[element]
        element_remote = element_info.get("repo")
        element_branch = element_info.get("branch", "main")
        elements_dir = element_info.get("elements_directory", ".")
        THIRD_PARTY_ELEMENT_SOURCES.append(
            ElementSource(
                element, parse_url(element_remote), element_branch, elements_dir
            )
        )
    LOG.info("Third-party elements updated.")
