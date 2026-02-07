import json
import os
import re
import secrets
import time
from base64 import b64decode, b64encode
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests
from Crypto.Cipher import AES

import rcds
import rcds.backend
from rcds.util import load_any
from rcds.util.jsonschema import DefaultValidatingDraft7Validator

options_schema_validator = DefaultValidatingDraft7Validator(
    schema=load_any(Path(__file__).parent / "options.schema.yaml")
)


class InstancerClient:
    """Client for cyber-instancer admin API."""

    def __init__(self, url: str, session_token: str):
        self.url = url.rstrip("/")
        self.session_token = session_token
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {session_token}"

    @staticmethod
    def generate_login_token(login_secret_key: str, admin_team_id: str) -> str:
        """Generate an encrypted login token from secret key and team ID.

        This creates a type-16 token compatible with cyber-instancer's LoginToken class.
        """
        key = b64decode(login_secret_key)
        if len(key) != 32:
            raise ValueError(
                "Invalid secret login key. Must be exactly 32 bytes, base64 encoded"
            )

        login_token = {
            "k": 16,
            "t": int(time.time()),
            "d": admin_team_id,
        }
        json_str = json.dumps(login_token, separators=(",", ":"))
        nonce = secrets.token_bytes(12)
        cipher = AES.new(key, AES.MODE_GCM, nonce)
        enc, mac = cipher.encrypt_and_digest(json_str.encode())
        return b64encode(nonce + enc + mac).decode("utf-8")

    @classmethod
    def from_credentials(
        cls, url: str, login_secret_key: str, admin_team_id: str
    ) -> "InstancerClient":
        """Create client by generating a login token and authenticating."""
        login_token = cls.generate_login_token(login_secret_key, admin_team_id)
        return cls.from_login_token(url, login_token)

    @classmethod
    def from_login_token(cls, url: str, login_token: str) -> "InstancerClient":
        """Create client by logging in with an encrypted login token."""
        resp = requests.post(
            f"{url.rstrip('/')}/api/accounts/login", data={"login_token": login_token}
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "ok":
            raise ValueError(f"Login failed: {data.get('msg', 'Unknown error')}")
        return cls(url, data["token"])

    def list_challenges(self) -> List[Dict[str, Any]]:
        """List all challenges from the instancer."""
        resp = self.session.get(f"{self.url}/api/challenges")
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "ok":
            raise RuntimeError(f"Failed to list challenges: {data}")
        return data.get("challenges", [])

    def create_challenge(
        self,
        chall_id: str,
        per_team: bool,
        cfg: Dict[str, Any],
        lifetime: int,
        boot_time: int,
        name: str,
        description: str,
        author: str,
        categories: List[str],
        tags: List[str],
        replace_existing: bool = True,
    ) -> None:
        """Create or replace a challenge."""
        form_data = {
            "chall_id": chall_id,
            "per_team": "true" if per_team else "false",
            "cfg": json.dumps(cfg),
            "lifetime": str(lifetime),
            "boot_time": str(boot_time),
            "name": name,
            "description": description,
            "author": author,
            "categories": " ".join(categories) if categories else "",
            "tags": " ".join(tags) if tags else "",
            "replace_existing": "true" if replace_existing else "false",
        }
        resp = self.session.post(
            f"{self.url}/api/admin/challenges/create", data=form_data
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") not in ("ok",):
            raise RuntimeError(f"Failed to create challenge {chall_id}: {data}")

    def delete_challenge(self, chall_id: str) -> None:
        """Delete a challenge."""
        resp = self.session.delete(
            f"{self.url}/api/admin/challenges/challenges/{chall_id}"
        )
        resp.raise_for_status()

    def get_challenge(self, chall_id: str) -> Optional[Dict[str, Any]]:
        """Get challenge info."""
        resp = self.session.get(f"{self.url}/api/admin/challenges/{chall_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "not_found":
            return None
        return data


class ContainerBackend(rcds.backend.BackendContainerRuntime):
    _project: rcds.Project
    _options: Dict[str, Any]
    _client: Optional[InstancerClient]

    def __init__(self, project: rcds.Project, options: Dict[str, Any]):
        self._project = project
        self._options = dict(options)  # Make a copy to avoid modifying original
        self._client = None

        # Read options from environment variables (env vars take precedence)
        env_mappings = {
            "url": "RCDS_INSTANCER_URL",
            "login_secret_key": "RCDS_INSTANCER_LOGIN_SECRET_KEY",
            "admin_team_id": "RCDS_INSTANCER_ADMIN_TEAM_ID",
        }
        for option_key, env_key in env_mappings.items():
            env_value = os.environ.get(env_key)
            if env_value:
                self._options[option_key] = env_value

        if not options_schema_validator.is_valid(self._options):
            raise ValueError("Invalid instancer backend options")

    def _get_client(self) -> InstancerClient:
        """Lazily create and return the instancer client."""
        if self._client is None:
            self._client = InstancerClient.from_credentials(
                self._options["url"],
                self._options["login_secret_key"],
                self._options["admin_team_id"],
            )
        return self._client

    def patch_challenge_schema(self, schema: Dict[str, Any]) -> None:
        """Add instancer-specific fields to challenge schema."""
        schema["properties"]["instancer"] = {
            "type": "object",
            "description": (
                "Configuration for the cyber-instancer backend. Only used when "
                "backend is set to 'instancer'."
            ),
            "properties": {
                "per_team": {
                    "type": "boolean",
                    "description": (
                        "Whether each team gets their own isolated instance. "
                        "If false, all teams share a single instance."
                    ),
                    "default": True,
                },
                "lifetime": {
                    "type": "integer",
                    "description": (
                        "How long (in seconds) an instance lives before it is "
                        "terminated. Teams can renew the instance to extend the "
                        "lifetime."
                    ),
                    "minimum": 1,
                },
                "boot_time": {
                    "type": "integer",
                    "description": (
                        "Time (in seconds) to wait after starting before showing "
                        "connection information to the user. Useful for challenges "
                        "that need time to initialize."
                    ),
                    "minimum": 0,
                    "default": 15,
                },
            },
            "default": {},
        }

    def _should_handle_challenge(self, challenge: rcds.Challenge) -> bool:
        """Check if this backend should handle the given challenge."""
        return self._project.get_backend_name_for_challenge(challenge) == "instancer"

    def commit(self, dry_run: bool = False, partial: bool = False) -> bool:
        """Deploy challenges to instancer."""
        # Get defaults from options
        defaults = self._options.get("defaults", {})
        default_per_team = defaults.get("per_team", True)
        default_lifetime = defaults.get("lifetime", 900)
        default_boot_time = defaults.get("boot_time", 15)

        # Track deployed challenge IDs for cleanup
        deployed_ids: Set[str] = set()

        # Process each challenge
        for challenge in self._project.challenges.values():
            # Skip if this challenge doesn't target instancer backend
            if not self._should_handle_challenge(challenge):
                continue

            instancer_config = challenge.config.get("instancer", {})

            # Skip if not deployed
            if not challenge.config.get("deployed", True):
                continue

            # Skip if no containers are specified
            if not challenge.config.get("containers"):
                continue

            chall_id = challenge.config["id"]
            deployed_ids.add(chall_id)

            if dry_run:
                print(f"[instancer] Would deploy {chall_id}")
                continue

            # Convert challenge to instancer format
            cfg = self._convert_challenge_config(challenge)

            # Get instancer-specific options
            per_team = instancer_config.get("per_team", default_per_team)
            lifetime = instancer_config.get("lifetime", default_lifetime)
            boot_time = instancer_config.get("boot_time", default_boot_time)

            # Get metadata
            name = challenge.config["name"]
            
            # Set template variables for Jinja templating
            challenge.context["link"] = "{instancer}"
            challenge.context["nc"] = "{instancer}"
            
            description = challenge.render_description()
            # Remove template strings with backticks (e.g., `{{nc}}`)
            description = re.sub(r"` ?\{.*?\} ?`", "", description)

            # Remove any remaining template strings (e.g., {instancer})
            description = re.sub(r"\{.*?\}", "", description)
            # Append footer
            if "description_footer" in self._options:
                description += f"\n\n{self._options['description_footer']}"

            author = challenge.config.get("author", "")
            if isinstance(author, list):
                author = ", ".join(author)

            # Get categories and tags
            categories = []
            category = challenge.config.get("category")
            if category:
                categories.append(category)

            tags = []
            for tag in challenge.config.get("tags", []):
                if isinstance(tag, dict):
                    # Tags in rcds are {metatag: value} format
                    tags.extend(tag.values())
                else:
                    tags.append(str(tag))

            print(f"[instancer] Deploying {chall_id}...")
            self._get_client().create_challenge(
                chall_id=chall_id,
                per_team=per_team,
                cfg=cfg,
                lifetime=lifetime,
                boot_time=boot_time,
                name=name,
                description=description,
                author=author,
                categories=categories,
                tags=tags,
                replace_existing=True,
            )

        # Delete challenges no longer in repo (unless partial deployment)
        if not partial and not dry_run and deployed_ids:
            try:
                remote_challenges = self._get_client().list_challenges()
                for remote in remote_challenges:
                    # The list endpoint returns challenge info in a specific format
                    challenge_info = remote.get("challenge_info")
                    remote_id = challenge_info.get("id")
                    if remote_id and remote_id not in deployed_ids:
                        print(f"[instancer] Deleting {remote_id}...")
                        self._get_client().delete_challenge(remote_id)
            except Exception as e:
                print(f"[instancer] Warning: Could not clean up old challenges: {e}")

        return True

    def _convert_challenge_config(self, challenge: rcds.Challenge) -> Dict[str, Any]:
        """Convert rcds challenge config to instancer cfg format."""
        containers_config = challenge.config.get("containers", {})
        expose_config = challenge.config.get("expose", {})
        domain = self._options.get("domain", "")

        # Build containers dict
        containers: Dict[str, Dict[str, Any]] = {}
        for name, container in containers_config.items():
            cont: Dict[str, Any] = {
                "image": container["image"],  # Already resolved by rcds
            }

            # Copy supported container fields from rcds to instancer format
            supported_fields = [
                "args", "command", "imagePullPolicy", "stdin", "stdinOnce",
                "terminationMessagePath", "terminationMessagePolicy", "tty",
                "workingDir", "env", "environment", "kubePorts", "ports",
                "securityContext", "hasEgress", "multiService"
            ]
            
            for field in supported_fields:
                if field in container:
                    cont[field] = container[field]

            # Copy resources (convert to string format if needed)
            if "resources" in container:
                cont["resources"] = self._convert_resources(container["resources"])

            containers[name] = cont

        # Build tcp and http expose maps
        tcp: Dict[str, List[int]] = {}
        http: Dict[str, List[List[Any]]] = {}  # [[port, subdomain], ...]

        for container_name, expose_rules in expose_config.items():
            for rule in expose_rules:
                target_port = rule["target"]

                if "tcp" in rule:
                    # TCP exposure - just list the port
                    if container_name not in tcp:
                        tcp[container_name] = []
                    tcp[container_name].append(target_port)

                elif "http" in rule:
                    # HTTP exposure
                    if container_name not in http:
                        http[container_name] = []

                    subdomain = rule["http"]
                    if isinstance(subdomain, dict) and "raw" in subdomain:
                        # Raw domain - use as-is
                        full_domain = subdomain["raw"]
                    else:
                        # Subdomain - append domain suffix if configured
                        if domain:
                            full_domain = f"{subdomain}.{domain}"
                        else:
                            full_domain = subdomain

                    http[container_name].append([target_port, full_domain])

        cfg: Dict[str, Any] = {"containers": containers}
        if tcp:
            cfg["tcp"] = tcp
        if http:
            cfg["http"] = http

        return cfg

    def _convert_resources(self, resources: Dict[str, Any]) -> Dict[str, Any]:
        """Convert resource specs to instancer format."""
        result: Dict[str, Any] = {}
        for key in ["limits", "requests"]:
            if key in resources:
                result[key] = {}
                for resource_type in ["cpu", "memory"]:
                    if resource_type in resources[key]:
                        value = resources[key][resource_type]
                        if isinstance(value, (int, float)):
                            if resource_type == "cpu":
                                # Convert numeric CPU to millicore string
                                result[key][resource_type] = f"{int(value * 1000)}m"
                            else:
                                # Convert numeric memory to string with appropriate units
                                result[key][resource_type] = str(int(value))
                        else:
                            # Keep string values as-is (e.g., "100m", "1Gi")
                            result[key][resource_type] = str(value)
        return result


class BackendsInfo(rcds.backend.BackendsInfo):
    HAS_CONTAINER_RUNTIME = True

    def get_container_runtime(
        self, project: rcds.Project, options: Dict[str, Any]
    ) -> ContainerBackend:
        return ContainerBackend(project, options)


def get_info() -> BackendsInfo:
    return BackendsInfo()
