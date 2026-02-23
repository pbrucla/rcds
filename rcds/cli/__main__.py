import importlib.metadata

import click

from .deploy import deploy


@click.group()
@click.version_option(importlib.metadata.version("rcds"))
def cli():
    pass


cli.add_command(deploy)


if __name__ == "__main__":
    cli()
