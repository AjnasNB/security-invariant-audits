"""Parse upstream YAML as data. !include is retained as a reference, not executed."""
import json
from pathlib import Path
import yaml


class DataLoader(yaml.SafeLoader):
    pass


DataLoader.add_constructor("!include", lambda loader, node: {"include_reference": loader.construct_scalar(node)})


if __name__ == "__main__":
    root = Path("/task/src/agentdojo/data/suites")
    print(json.dumps([
        {"path": str(path.relative_to("/task")), "data": yaml.load(path.read_text(), Loader=DataLoader)}
        for path in sorted(root.rglob("*.yaml"))
    ], default=str))
