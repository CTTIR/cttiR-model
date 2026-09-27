from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

from .errors import ProjectError
from .provenance import decode_json, read_json


@lru_cache(maxsize=16)
def validator(name: str) -> Draft202012Validator:
    if name not in {"config", "request", "response", "training-record", "release", "corpus"}:
        raise ProjectError("unknown_schema", "Unknown contract.")
    schema = decode_json(files("cttir_model").joinpath("schemas", name + ".schema.json").read_bytes())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate(value: Any, name: str) -> None:
    error = next(validator(name).iter_errors(value), None)
    if error is not None:
        # Avoid reflecting untrusted values (including secrets) in CLI/service errors.
        path = "/".join(str(part) for part in error.schema_path)
        raise ProjectError("schema_invalid", f"{name} contract failed at schema rule {path}.")


@dataclass(frozen=True)
class Config:
    values: dict
    root: Path

    @property
    def artifacts(self) -> Path:
        return self.path(self.values["project"]["artifact_root"])

    @property
    def limit(self) -> int:
        return self.values["execution"]["max_input_bytes"]

    def path(self, value: str) -> Path:
        path = Path(value).expanduser()
        return (self.root / path).resolve()


def load_config(path: Path) -> Config:
    path = path.resolve()
    value = read_json(path)
    validate(value, "config")
    for role in ("supervisor", "specialist"):
        endpoint = value["models"][role]["endpoint"]
        if endpoint:
            parsed = urlsplit(endpoint)
            if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"}
                    or parsed.username or parsed.password or parsed.query or parsed.fragment):
                raise ProjectError("endpoint_policy", "Only credential-free literal loopback HTTP endpoints are supported.")
    # Repository profiles live in configs/; standalone configs resolve beside themselves.
    root = path.parent.parent if path.parent.name == "configs" else path.parent
    config = Config(value, root)
    if value["corpus"]["retrieval"] != "lexical":
        raise ProjectError("unsupported_backend", "Only local lexical retrieval is implemented.")
    if value["release"]["publish_enabled"]:
        raise ProjectError("publication_disabled", "Publication is unavailable in the CPU milestone.")
    return config
