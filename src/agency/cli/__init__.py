import click
from agency.cli.init import init_command
from agency.cli.serve import serve_command
from agency.cli.register import register_command
from agency.cli.primitives import primitives_command
from agency.cli.upgrade import upgrade_command
from agency.cli.token import token_group
from agency.cli.mcp import mcp_command
from agency.cli.project import project_create_command
from agency.cli.setup import client_setup_command
from agency.cli.skills import skills_install_command


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
main.add_command(mcp_command)

# agency project create
project_group = click.Group("project")
project_group.add_command(project_create_command, name="create")
main.add_command(project_group)

# agency client setup
client_group = click.Group("client")
client_group.add_command(client_setup_command, name="setup")
main.add_command(client_group)

# agency skills install
skills_group = click.Group("skills")
skills_group.add_command(skills_install_command, name="install")
main.add_command(skills_group)
