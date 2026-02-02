from pathlib import Path
from sys import exit

import click

import rcds
import rcds.challenge.docker
from rcds.util import SUPPORTED_EXTENSIONS, find_files


@click.command()
@click.option(
    "--no-docker",
    "-D",
    is_flag=True,
    help="Do not build docker containers or deploy to Kubernetes.",
)
@click.option(
    "--challenge-dir",
    "-c",
    default=[],
    multiple=True,
    help="Only scan for challenges in a specified subdirectory. Can be specified multiple times.",
)
def deploy(no_docker: bool, challenge_dir: list[str]) -> None:
    try:
        project_config = find_files(["rcds"], SUPPORTED_EXTENSIONS, recurse=True)[
            "rcds"
        ].parent
    except KeyError:
        click.echo("Could not find project root!")
        exit(1)
    click.echo(f"Loading project at {project_config}")
    project = rcds.Project(project_config)
    click.echo("Initializing backends...")
    project.load_backends()
    click.echo("Loading challenges")
    if len(challenge_dir) == 0:
        scan_paths = None
    else:
        scan_paths = [Path(p).resolve() for p in challenge_dir]
        for p in scan_paths:
            if not p.is_relative_to(project.root):
                click.echo(
                    f'Error: Challenge dir "{p}" is not inside project root',
                    err=True,
                )
                return
    partial = scan_paths is not None
    project.load_all_challenges(scan_paths=scan_paths)
    for challenge in project.challenges.values():
        if not no_docker:
            cm = rcds.challenge.docker.ContainerManager(challenge)
            for container_name, container in cm.containers.items():
                click.echo(
                    f"{challenge.config['id']}: checking container {container_name}"
                )
                if not container.is_built():
                    click.echo(
                        f"{challenge.config['id']}: building container {container_name}"
                        f" ({container.get_full_tag()})"
                    )
                    container.build()
        challenge.create_transaction().commit()
    if project.container_backends:
        # Only commit backends that have challenges assigned to them
        backends_with_challenges = project.get_backends_with_challenges()
        if backends_with_challenges:
            for backend_name, backend in backends_with_challenges.items():
                if not no_docker:
                    click.echo(f"Committing container backend: {backend_name}")
                else:
                    click.echo(f"Dry running container backend: {backend_name}")
                backend.commit(dry_run=no_docker, partial=partial)
        else:
            click.echo("WARN: no challenges assigned to any container backend, skipping...")
    else:
        click.echo("WARN: no container backend, skipping...")
    if project.scoreboard_backend is not None:
        click.echo("Commiting scoreboard backend")
        project.scoreboard_backend.commit(partial=partial)
    else:
        click.echo("WARN: no scoreboard backend, skipping...")
