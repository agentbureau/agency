import click
from agency.cli.init import init_command
from agency.cli.serve import serve_command
from agency.cli.register import register_command
from agency.cli.primitives import primitives_command
from agency.cli.upgrade import upgrade_command
from agency.cli.token import token_group


@click.group()
@click.version_option(package_name="agency-engine")
def main():
    """Agency — self-hosted LLM agent composition engine."""


main.add_command(init_command)
main.add_command(serve_command)
main.add_command(register_command)
main.add_command(primitives_command)
main.add_command(upgrade_command)
main.add_command(token_group)
