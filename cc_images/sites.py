import os

import yaml


class ChameleonSite:
    def __init__(self, name: str,
                 is_baremetal: bool,
                 cloud: str,
                 image_container: str) -> None:
        self.name = name
        self.is_baremetal = is_baremetal
        self.cloud = cloud
        self.image_container = image_container


def get_sites() -> "list[ChameleonSite]":
    """
    Loads sites.yaml
    """
    application_path = os.path.join(os.path.dirname(__file__), "..")
    default_sites_path = os.path.join(application_path, "config", "sites.yaml")
    sites_path = os.getenv("CC_SITES_CONFIG", default_sites_path)
    with open(sites_path, "r") as f:
        all_sites = yaml.safe_load(f)
    output = []
    for site_name in all_sites:
        site = all_sites.get(site_name, {})
        is_baremetal = site.get("is_baremetal", False)
        cloud = site.get("cloud")
        if not cloud:
            raise ValueError("Missing required site attribute cloud")
        image_container = site.get("image_container", "chameleon-images")
        output.append(ChameleonSite(site_name, is_baremetal,
                                    cloud, image_container))
    return output
