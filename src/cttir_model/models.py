"""Small public metadata only. This module cannot acquire model weights."""

import hashlib
import re
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit

from .config import Config
from .errors import ProjectError
from .provenance import atomic_json, decode_json, fingerprint, now


METADATA_FILES = {"config.json", "tokenizer_config.json", "special_tokens_map.json",
                  "processor_config.json", "preprocessor_config.json", "chat_template.jinja",
                  "README.md", "LICENSE", "LICENSE.txt", "LICENSE.md", "NOTICE"}


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname != "huggingface.co":
            raise ProjectError("metadata_redirect", "Metadata redirects must stay on huggingface.co.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_metadata(url: str) -> bytes:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "huggingface.co":
        raise ProjectError("metadata_host", "Only public Hugging Face metadata is supported.")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), SameHostRedirect())
    try:
        with opener.open(urllib.request.Request(url, headers={"User-Agent": "cttir-model-metadata/0.1"}), timeout=10) as response:
            data = response.read(524289)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ProjectError("metadata_unavailable", "Public model metadata could not be fetched within the budget.") from exc
    if len(data) > 524288:
        raise ProjectError("metadata_limit", "Metadata file exceeds 512 KiB; no larger download was attempted.")
    return data


def resolve_model(repo: str, revision: str | None = None, fetch=fetch_metadata) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ProjectError("model_id", "Expected an explicit owner/model identifier.")
    if revision is not None and not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ProjectError("model_revision", "Configured revisions must be immutable SHAs.")
    url = f"https://huggingface.co/api/models/{repo}/revision/{revision or 'main'}?blobs=true"
    metadata_raw = fetch(url)
    metadata = decode_json(metadata_raw)
    if not isinstance(metadata, dict) or not re.fullmatch(r"[a-f0-9]{40}", str(metadata.get("sha", ""))):
        raise ProjectError("model_metadata", "Model metadata has no immutable revision.")
    resolved = metadata["sha"]
    if revision and resolved != revision:
        raise ProjectError("model_revision", "Server returned a different revision.")
    siblings = metadata.get("siblings", [])
    if not isinstance(siblings, list) or len(siblings) > 1000:
        raise ProjectError("model_metadata", "Unexpected file manifest.")
    names = {row.get("rfilename") for row in siblings if isinstance(row, dict)}
    records, content = [], {}
    for name in sorted(METADATA_FILES & names):
        raw = fetch(f"https://huggingface.co/{repo}/raw/{resolved}/{quote(name)}")
        content[name] = raw.decode("utf-8")
        records.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    if "config.json" not in content:
        raise ProjectError("model_config", "Exact-revision config.json is missing.")
    model_config = decode_json(content["config.json"].encode())
    manifest = [{"path": row.get("rfilename"), "bytes": row.get("size"),
                 "lfs_sha256": row.get("lfs", {}).get("sha256")}
                for row in siblings if isinstance(row, dict)]
    return {"repo_id": repo, "revision": resolved, "metadata_files": records,
            "metadata_content": content, "upstream_files": manifest,
            "model_type": model_config.get("model_type"), "architectures": model_config.get("architectures"),
            "declared_dtype": model_config.get("dtype", model_config.get("torch_dtype")),
            "quantization_config": model_config.get("quantization_config"),
            "license_declaration": (metadata.get("cardData") or {}).get("license"),
            "legal_review": "pending", "checkpoint_strategy": "unresolved",
            "effective_base_fingerprint": None, "training_compatible": False,
            "weights_downloaded": False}


def resolve(config: Config) -> dict:
    models = {role: resolve_model(row["repo_id"], row["revision"])
              for role, row in config.values["models"].items()}
    payload = {"schema_version": 1, "models": models, "metadata_only": True}
    digest = fingerprint(payload)
    path = config.artifacts / "model-locks" / (digest + ".json")
    atomic_json(path, payload)
    atomic_json(config.artifacts / "model-locks" / (digest + ".checked.json"), {"checked_at": now(), "lock_sha256": digest})
    return {"status": "metadata_resolved", "path": str(path), "lock_sha256": digest,
            "models": {role: {k: row[k] for k in ("repo_id", "revision", "architectures", "quantization_config")}
                       for role, row in models.items()}, "training_ready": False, "weights_downloaded": False}
