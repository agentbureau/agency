import click


@click.command("upgrade")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation")
def upgrade_command(yes: bool):
    """Upgrade Agency to the latest version."""
    click.echo("Checking for updates via GitHub releases API...")
    click.echo("(Not yet implemented — see Task 36)")
