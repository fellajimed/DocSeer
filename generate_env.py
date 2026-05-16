from pathlib import Path
from dotenv import set_key, find_dotenv, dotenv_values
from docseer import CACHE_FOLDER

root_path = Path(__file__).resolve().absolute().parent

env_file = find_dotenv()
if not env_file:
    env_file = ".env"
    with open(env_file, "a"):
        pass

set_key(env_file, "DOCSEER_CACHE_FOLDER", str(CACHE_FOLDER))

assert (root_path / "ports.env").is_file
ports_mapping = dotenv_values(root_path / "ports.env")

for key, value in ports_mapping.items():
    if value is not None:
        set_key(env_file, key, value)

print("✅ Updated .env")
