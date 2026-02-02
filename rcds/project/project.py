from pathlib import Path
from typing import Any, Dict, List, Optional

import docker  # type: ignore
from jinja2 import Environment

import click

from rcds.util import SUPPORTED_EXTENSIONS, find_files

from ..backend import BackendContainerRuntime, BackendScoreboard, load_backend_module
from ..challenge import Challenge, ChallengeLoader
from . import config
from .assets import AssetManager


class Project:
    """
    An rCDS project; the context that all actions are done within
    """

    root: Path
    config: dict
    challenges: Dict[Path, Challenge]
    challenge_loader: ChallengeLoader

    asset_manager: AssetManager

    # Multiple container backends, keyed by their resolve name
    container_backends: Dict[str, BackendContainerRuntime]
    # Order of container backends (for determining first/default)
    container_backend_order: List[str]
    # Default container backend name (from config)
    default_container_backend: Optional[str] = None
    scoreboard_backend: Optional[BackendScoreboard] = None

    jinja_env: Environment
    docker_client: Any

    def __init__(
        self, root: Path, docker_client: Optional[docker.client.DockerClient] = None
    ):
        """
        Create a project
        """
        root = root.resolve()
        try:
            cfg_file = find_files(
                ["rcds"], SUPPORTED_EXTENSIONS, path=root, recurse=False
            )["rcds"]
        except KeyError:
            raise ValueError(f"No config file found at '{root}'")
        self.root = root
        self.config = config.load_config(cfg_file)
        self.challenges = dict()
        self.container_backends = {}
        self.container_backend_order = []
        self.scoreboard_backend = None
        self.challenge_loader = ChallengeLoader(self)
        self.asset_manager = AssetManager(self)
        self.jinja_env = Environment(autoescape=False)
        if docker_client is not None:
            self.docker_client = docker_client
        else:
            self.docker_client = docker.from_env()

    def load_all_challenges(self, scan_paths: list[Path] | None = None) -> None:
        if scan_paths is None:
            scan_paths = [self.root]
        chall_files: set[Path] = set()
        for ext in SUPPORTED_EXTENSIONS:
            for base in scan_paths:
                chall_files |= set(base.rglob(f"challenge.{ext}"))
        for chall_file in chall_files:
            path = chall_file.parent
            self.challenges[path.relative_to(self.root)] = self.challenge_loader.load(
                path
            )

    def get_challenge(self, relPath: Path) -> Challenge:
        return self.challenges[relPath]

    def load_backends(self) -> None:
        # Load default container backend from config
        self.default_container_backend = self.config.get("defaultContainerBackend")

        for backend_config in self.config["backends"]:
            backend_name = backend_config["resolve"]
            backend_info = load_backend_module(backend_name)

            # Still only one scoreboard backend (first one wins)
            if self.scoreboard_backend is None and backend_info.HAS_SCOREBOARD:
                self.scoreboard_backend = backend_info.get_scoreboard(
                    self, backend_config["options"]
                )

            # Load ALL container backends into dict
            if backend_info.HAS_CONTAINER_RUNTIME:
                self.container_backends[backend_name] = (
                    backend_info.get_container_runtime(self, backend_config["options"])
                )
                self.container_backend_order.append(backend_name)

        # TODO: maybe don't reinitialize here?
        self.challenge_loader = ChallengeLoader(self)

    def get_backend_for_challenge(
        self, challenge: Challenge
    ) -> Optional[BackendContainerRuntime]:
        """Get the container backend that should handle a specific challenge."""
        # Check if challenge specifies a backend
        backend_name = challenge.config.get("backend")

        # Fall back to default if not specified
        if backend_name is None:
            backend_name = self.default_container_backend

        # Fall back to first backend if still not specified
        if backend_name is None and self.container_backend_order:
            backend_name = self.container_backend_order[0]

        if backend_name is None:
            return None

        return self.container_backends.get(backend_name)

    def get_backend_name_for_challenge(self, challenge: Challenge) -> Optional[str]:
        """Get the name of the container backend that should handle a specific challenge."""
        backend_name = challenge.config.get("backend")
        if backend_name is None:
            backend_name = self.default_container_backend
        if backend_name is None and self.container_backend_order:
            backend_name = self.container_backend_order[0]
        return backend_name

    def get_backends_with_challenges(self) -> Dict[str, BackendContainerRuntime]:
        """Get only the container backends that have challenges assigned to them."""
        backends_with_challenges = {}
        for backend_name, backend in self.container_backends.items():
            # Check if any challenge uses this backend
            for challenge in self.challenges.values():
                if self.get_backend_name_for_challenge(challenge) == backend_name:
                    backends_with_challenges[backend_name] = backend
                    break  # Found at least one challenge, no need to check more
        return backends_with_challenges
