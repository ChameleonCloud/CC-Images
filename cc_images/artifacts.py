import openstack


class BuildArtifact:
    """
    Represents a remote file in an object store that will be downloaded by an image.
    Essentially responsible for generating download links for these files.
    """

    def __init__(self, name: str, obj: str, site: str):
        self.name = name
        self.obj = obj.strip("/ ")
        self.conn = openstack.connect(cloud=site)

    @property
    def download_url(self) -> str:
        return self.conn.object_store.generate_temp_url(
            path=f"/v1/AUTH_{self.conn.current_project_id}/{self.obj}",
            seconds=60 * 60,
            method="GET",
        )
