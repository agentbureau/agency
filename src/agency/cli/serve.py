import click
import uvicorn


@click.command("serve")
@click.option("--host", default="127.0.0.1", help="Host to bind")
@click.option("--port", default=8000, type=int, help="Port to bind")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload")
def serve_command(host: str, port: int, reload: bool):
    """Start the Agency API server."""
    uvicorn.run(
        "agency.api.app:app",
        host=host,
        port=port,
        reload=reload,
    )
