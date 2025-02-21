import argparse
import sys

from cc_images.config import get_supported_image_names, Architecture


class CCImagesArgs:
    """
    Packages arguments in a structure more strictly defined than argparse's ``Namespace``
    """

    def __init__(
        self,
        do_build: bool,
        do_push: bool,
        destroy_cache: bool,
        n_tasks: int,
        scope: str,
        arch: "list[Architecture]",
        images: "list[str]",
    ):
        self.do_build: bool = do_build
        self.do_push: bool = do_push
        self.destroy_cache: bool = destroy_cache
        self.n_tasks: int = n_tasks
        self.scope: str = scope
        self.arch: list[Architecture] = arch
        self.images: set[str] = set(images)

        if not (do_build or do_push):
            raise ValueError(
                "cc-images not configured to build or push! Run with -h for context."
            )


def parse_args() -> CCImagesArgs:
    """
    Handles parsing commandline arguments
    """
    arg_parser = argparse.ArgumentParser(
        description="Chameleon official image building/publishing tool, "
        "based on OpenStack's diskimage-builder"
    )

    arg_parser.add_argument(
        "-b",
        "--build",
        help="Build new versions of the listed image tags",
        dest="do_build",
        action="store_true",
        default=False,
    )

    arg_parser.add_argument(
        "-p",
        "--push",
        help="Push the most recent version of the image(s) in the cache. "
        "When combined with -b, pushes the image(s) just built.",
        dest="do_push",
        action="store_true",
        default=False,
    )

    arg_parser.add_argument(
        "-f",
        "--force",
        help="Force a complete rebuild of the image(s) without reusing the cache. "
        "Destroys the cache for the image(s) in the process.",
        dest="destroy_cache",
        action="store_true",
        default=False,
    )

    arg_parser.add_argument(
        "-t",
        "--tasks",
        help="The number of build tasks to run in parallel, where applicable. "
        "By default, only one task is run at a time, as it can get very resource-intensive",
        dest="n_tasks",
        type=int,
        default=1,
    )

    arg_parser.add_argument(
        "-s",
        "--scope",
        help="The scope for where to push images (supports prod currently). "
        "By default, this tool operates in prod.",
        dest="scope",
        type=str,
        default="prod",
    )

    arg_parser.add_argument(
        "-a",
        "--architecture",
        help="Comma-separated list of architectures to build/push. "
        "Uses all supported architectures for each image by default.",
        dest="architectures",
        type=lambda s: [Architecture(a.strip().lower()) for a in s.split(",")],
        default=list(Architecture),
        metavar=f"[{','.join(str(a.value) for a in Architecture)}]",
    )

    arg_parser.add_argument(
        "images",
        help="The image tag(s) to build",
        type=str,
        nargs="+",
        choices=get_supported_image_names(),
    )

    namespace = arg_parser.parse_args()
    return CCImagesArgs(
        namespace.do_build,
        namespace.do_push,
        namespace.destroy_cache,
        namespace.n_tasks,
        namespace.scope,
        namespace.architectures,
        namespace.images,
    )
