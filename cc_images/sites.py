import os

import yaml


class ChameleonSite:
    def __init__(self, name: str, is_baremetal: bool, cloud: str) -> None:
        self.name = name
        self.is_baremetal = is_baremetal
        self.cloud = cloud


def get_sites() -> list[ChameleonSite]:
    """
    Loads sites.yaml
    """
    this_dir = os.path.dirname(__file__)
    cc_sites_path = os.getenv("CC_SITES_CONFIG", os.path.join(this_dir, "sites.yaml"))
    with open(cc_sites_path, "r") as f:
        all_sites = yaml.safe_load(f)
    output = []
    for site_name in all_sites:
        site = all_sites.get(site_name, {})
        is_baremetal = site.get("is_baremetal", False)
        cloud = site.get("cloud")
        if not cloud:
            raise ValueError("Missing required site attribute cloud")
        output.append(ChameleonSite(site_name, is_baremetal, cloud))
    return output
