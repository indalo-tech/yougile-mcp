import json

import pytest

from yougile_mcp.config import ConfigError, Settings, WorkspaceConfig, load_workspace_config


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")


def test_repo_config_overrides_global(tmp_path):
    home, repo = tmp_path / "home", tmp_path / "repo"
    (repo / "src" / "deep").mkdir(parents=True)
    home.mkdir()
    write(
        home / ".yougile-mcp.json",
        {"role": "member", "confirm_projects": ["Клиенты"], "instructions": ["a", "b"]},
    )
    write(
        repo / ".yougile.json",
        {"project": "Разработка", "board": "Сайт", "workflows": {"Клиенты / Сайт": ["A", "B"]}},
    )
    cfg = load_workspace_config(cwd=repo / "src" / "deep", env={}, home=home)
    assert (cfg.role, cfg.project, cfg.board) == ("member", "Разработка", "Сайт")
    assert cfg.confirm_projects == ["Клиенты"]
    assert cfg.workflows == {"Клиенты / Сайт": ["A", "B"]}
    assert cfg.instructions == "a\nb"
    assert len(cfg.sources) == 2


def test_explicit_config_env(tmp_path):
    write(tmp_path / "custom.json", {"role": "reader"})
    cfg = load_workspace_config(
        cwd=tmp_path,
        env={"YOUGILE_CONFIG": str(tmp_path / "custom.json")},
        home=tmp_path / "nohome",
    )
    assert cfg.role == "reader"
    with pytest.raises(ConfigError, match="missing file"):
        load_workspace_config(
            cwd=tmp_path, env={"YOUGILE_CONFIG": str(tmp_path / "nope.json")}, home=tmp_path
        )


def test_keys_are_rejected_in_config_files():
    with pytest.raises(ConfigError, match="YOUGILE_API_KEY"):
        WorkspaceConfig.from_dict({"api_key": "x"})


def test_validation():
    with pytest.raises(ConfigError, match="role"):
        WorkspaceConfig.from_dict({"role": "owner"})
    with pytest.raises(ConfigError, match="list of strings"):
        WorkspaceConfig.from_dict({"deny": [1]})
    cfg = WorkspaceConfig.from_dict({"projects": "Разработка", "extra": 1})
    assert cfg.projects == ["Разработка"]
    assert any("unknown key" in w for w in cfg.warnings)


def test_settings_from_env(tmp_path):
    s = Settings.from_env(
        {
            "YOUGILE_API_KEY": " k ",
            "YOUGILE_BASE_URL": "https://ru.yougile.com/api-v2/",
            "YOUGILE_RATE_LIMIT": "30",
            "YOUGILE_MCP_STATE_DIR": str(tmp_path),
        }
    )
    assert (s.api_key, s.base_url, s.rate_limit, s.state_dir) == (
        "k",
        "https://ru.yougile.com",
        30,
        tmp_path,
    )
    assert Settings.from_env({}).api_key is None
    with pytest.raises(ConfigError):
        Settings.from_env({"YOUGILE_RATE_LIMIT": "many"})
