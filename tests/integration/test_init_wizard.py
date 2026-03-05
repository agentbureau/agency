from click.testing import CliRunner
from agency.cli.init import init_command


def test_init_creates_config_and_keypair(tmp_path):
    runner = CliRunner()
    result = runner.invoke(init_command, catch_exceptions=False, input="\n".join([
        "https://api.anthropic.com/v1",  # endpoint
        "claude-sonnet-4-6",             # model
        "sk-test-key",                   # api key
        "test@example.com",              # email
        "discretion",                    # oversight
        "300",                           # timeout
        "n",                             # register? no
    ]) + "\n", env={"AGENCY_STATE_DIR": str(tmp_path)})
    assert result.exit_code == 0, result.output
    assert (tmp_path / "agency.toml").exists()
    assert (tmp_path / "keys" / "agency.ed25519").exists()
