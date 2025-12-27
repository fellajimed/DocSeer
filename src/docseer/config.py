import yaml
from copy import deepcopy
from pathlib import Path


def get_main_config(user_config: dict | None):
    return deep_merge(default_config(), user_config)


def read_config(fname: str | Path):
    with open(fname, "r") as file:
        return yaml.safe_load(file)


def default_config():
    current_path = Path(__file__).resolve().absolute().parent
    return read_config(current_path / "config.yaml")


def deep_merge(default: dict, user: dict | None) -> dict:
    """
    Recursively merge user config into default config.
    User values override defaults.
    """
    result = deepcopy(default)
    if user is None:
        return result

    for key, value in user.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result
