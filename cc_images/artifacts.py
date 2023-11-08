from typing import Union

import openstack
from openstack.exceptions import ConfigException


class BuildArtifact:
    """
    Represents a remote file in an object store that will be downloaded by an image.
    Essentially responsible for generating download links for these files.
    """

    def __init__(self, name: str, obj: str, site: str):
        self.name = name
        self.obj = obj.strip("/ ")
        try:
            self.conn = openstack.connect(cloud=site)
        except ConfigException as ex:
            self.conn = None


    @property
    def download_url(self) -> Union[str, None]:
        try:
            return_url = self.conn.object_store.generate_temp_url(
            path=f"/v1/AUTH_{self.conn.current_project_id}/{self.obj}",
            seconds=60 * 60,
            method="GET",
        )
        except ConfigException as ex:
            return None
        else:
            return return_url

