"""Check a model registration pull request before the workflow merges it.

Standard library only. Nothing from the pull request is checked out or executed:
files are read from git objects, and checkpoints are read by an unpickler that
can only rebuild float32 tensors. CAESAR's register_model.py imports this module
from a UFL_MODELS clone to prepare requests, so the client and the workflow apply
the same rules.

Usage: python3 test/check_registration.py --base REV --head REV \
           --author LOGIN --author-id ID --repository OWNER/REPO
"""

import argparse
import array
import collections
import copy
import hashlib
import html
import io
import json
import math
import pickle
import re
import subprocess
import sys
import zipfile

ARCHITECTURE = "caesar-bcrn-v1"
LOGIN = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
MAX_CHECKPOINT_BYTES = 100 * 1024 * 1024  # GitHub refuses larger files in a push
MODEL_KEYS = {
    "name",
    "display_name",
    "description",
    "filename",
    "sha256",
    "min_dims",
    "max_dims",
    "registration_id",
    "id",
    "architecture",
    "owner",
    "owner_id",
    "url",
}
README_START = "<!-- BEGIN GENERATED MODEL LIST -->"
README_END = "<!-- END GENERATED MODEL LIST -->"


def validate_model(model):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", model["name"]):
        raise ValueError("Invalid model name")
    if not re.fullmatch(r"[0-9a-f]{64}", model["sha256"]):
        raise ValueError("Invalid checkpoint SHA-256")
    if type(model.get("registration_id")) is not int or model["registration_id"] <= 0:
        raise ValueError("A positive UFL registration number is required")
    if model["id"] != f'ufl:{model["registration_id"]}@sha256:{model["sha256"]}':
        raise ValueError(
            "Model identity does not match registration number and checkpoint hash"
        )
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.pt", model["filename"]):
        raise ValueError("Invalid checkpoint filename")
    if not (
        type(model["min_dims"]) is int
        and type(model["max_dims"]) is int
        and 2 <= model["min_dims"] <= model["max_dims"] <= 5
    ):
        raise ValueError("Supported dimensions must be within 2D–5D")
    if not model.get("description") or model.get("architecture") != ARCHITECTURE:
        raise ValueError("Missing description or unsupported model architecture")
    if not model["url"].startswith("https://"):
        raise ValueError("Checkpoint URL must use HTTPS")
    if not re.fullmatch(LOGIN, model.get("owner", "")):
        raise ValueError("Every registration requires a GitHub owner")
    if type(model.get("owner_id")) is not int or model["owner_id"] <= 0:
        raise ValueError("Every registration requires a stable GitHub owner ID")


def validate_catalog(catalog):
    if type(catalog.get("schema_version")) is not int or catalog["schema_version"] != 1:
        raise ValueError("Unsupported catalog schema")
    seen = {
        key: set() for key in ("name", "registration_id", "id", "sha256", "filename")
    }
    for model in catalog["models"] + catalog.get("retired_models", []):
        validate_model(model)
        for key, values in seen.items():
            if model[key] in values:
                raise ValueError(f"Duplicate {key}: {model[key]}")
            values.add(model[key])
    if catalog["default_model"] not in {m["name"] for m in catalog["models"]}:
        raise ValueError("Default must be an active model")


def admin_ids(policy):
    if policy.get("schema_version") != 1:
        raise ValueError("Unsupported administrator policy schema")
    ids = {value.get("id") for value in policy["admins"]}
    if not ids or any(type(value) is not int or value <= 0 for value in ids):
        raise ValueError("Invalid administrator policy")
    return ids


def model_list(catalog):
    """Render the public list; must match CAESAR's registry_catalog.model_list."""

    def cell(value):
        return (
            html.escape(str(value), quote=False)
            .replace("|", "&#124;")
            .replace("\n", " ")
            .replace("\r", " ")
        )

    lines = [
        README_START,
        "",
        "| Registration | Model | Owner | Status | Checkpoint | Dimensions | Description |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for status, models in (
        ("Active", catalog["models"]),
        ("Retired", catalog.get("retired_models", [])),
    ):
        for model in sorted(models, key=lambda m: m["registration_id"]):
            state = status
            if status == "Active" and model["name"] == catalog["default_model"]:
                state = "Active (default)"
            values = [
                model["registration_id"],
                f"{model['display_name']} ({model['name']})",
                model.get("owner", "Unassigned"),
                state,
                model["filename"],
                f"{model['min_dims']}D–{model['max_dims']}D",
                model["description"],
            ]
            lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    return "\n".join([*lines, "", README_END])


def render_readme(catalog, text):
    block = model_list(catalog)
    if README_START not in text and README_END not in text:
        return text.rstrip() + "\n\n" + block + "\n"
    if text.count(README_START) != 1 or text.count(README_END) != 1:
        raise ValueError("README must contain exactly one model list marker pair")
    start, end = text.index(README_START), text.index(README_END)
    if start >= end:
        raise ValueError("README model list markers are reversed")
    return text[:start] + block + text[end + len(README_END) :]


def register(
    catalog,
    *,
    name,
    display_name,
    description,
    filename,
    sha256,
    min_dims,
    max_dims,
    owner,
    owner_id,
    url,
):
    """Return the catalog with one new model under the next unused number."""
    for field, value, limit in (
        ("display_name", display_name, 120),
        ("description", description, 4000),
    ):
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError(f"Invalid {field}")
    result = copy.deepcopy(catalog)
    number = 1 + max(
        (
            m["registration_id"]
            for m in result["models"] + result.get("retired_models", [])
        ),
        default=0,
    )
    result["models"].append(
        dict(
            name=name,
            display_name=display_name,
            description=description,
            filename=filename,
            sha256=sha256,
            min_dims=min_dims,
            max_dims=max_dims,
            registration_id=number,
            id=f"ufl:{number}@sha256:{sha256}",
            architecture=ARCHITECTURE,
            owner=owner,
            owner_id=owner_id,
            url=url,
        )
    )
    validate_catalog(result)
    return result


def retire(catalog, name, default_model=None):
    """Return the catalog with an active model moved to retired_models.

    Authorization is checked against the pull request author by check_pull_request.
    """
    result = copy.deepcopy(catalog)
    model = next((m for m in result["models"] if m["name"] == name), None)
    if model is None:
        raise ValueError(f"No active model named {name}")
    result["models"].remove(model)
    result.setdefault("retired_models", []).append(model)
    if default_model is not None:
        result["default_model"] = default_model
    if result["default_model"] == name:
        raise ValueError("Retiring the default requires a replacement default")
    validate_catalog(result)
    return result


class _Unpickler(pickle.Unpickler):
    """Rebuild only what a float32 state_dict needs; refuse every other object."""

    def find_class(self, module, name):
        allowed = {
            ("collections", "OrderedDict"): collections.OrderedDict,
            ("torch._utils", "_rebuild_tensor_v2"): _Tensor,
            ("torch", "FloatStorage"): _FloatStorage,
        }
        if (module, name) not in allowed:
            raise ValueError(
                f"Checkpoint contains {module}.{name}; only float32 tensors are accepted"
            )
        return allowed[module, name]

    def persistent_load(self, pid):
        if not (
            isinstance(pid, tuple)
            and len(pid) == 5
            and pid[:2] == ("storage", _FloatStorage)
            and isinstance(pid[2], str)
            and type(pid[4]) is int
        ):
            raise ValueError("Checkpoint storage is not float32")
        return pid[2], pid[4]


class _FloatStorage:
    pass


class _Tensor:
    def __init__(self, storage, offset, shape, stride, *_):
        self.storage, self.offset = storage, offset
        self.shape, self.stride = tuple(shape), tuple(stride)


def read_checkpoint(data):
    """Return {parameter name: shape} for a PyTorch state_dict archive.

    Checks that every tensor is float32, fits in its storage, and is finite.
    """
    if len(data) > MAX_CHECKPOINT_BYTES:
        raise ValueError("Checkpoint exceeds the 100 MiB limit")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        pickles = [n for n in archive.namelist() if re.fullmatch(r"[^/]+/data\.pkl", n)]
        if len(pickles) != 1:
            raise ValueError("Checkpoint is not a PyTorch archive")
        root = pickles[0][: -len("data.pkl")]
        if f"{root}byteorder" in archive.namelist():
            if archive.read(f"{root}byteorder") != b"little":
                raise ValueError("Checkpoint byte order must be little-endian")
        state = _Unpickler(io.BytesIO(archive.read(pickles[0]))).load()
        if not isinstance(state, dict) or not state:
            raise ValueError("Checkpoint must be a non-empty state_dict")
        shapes, checked = {}, set()
        for name, tensor in state.items():
            if type(name) is not str or not isinstance(tensor, _Tensor):
                raise ValueError("Checkpoint must map parameter names to tensors")
            key, numel = tensor.storage
            if (
                type(tensor.offset) is not int
                or tensor.offset < 0
                or numel < 0
                or len(tensor.shape) != len(tensor.stride)
                or any(type(size) is not int or size < 0 for size in tensor.shape)
                or any(type(step) is not int or step < 0 for step in tensor.stride)
            ):
                raise ValueError(f"{name}: invalid tensor layout")
            if key not in checked:
                values = array.array("f")
                values.frombytes(archive.read(f"{root}data/{key}"))
                if len(values) != numel:
                    raise ValueError(f"{name}: storage size does not match")
                if sys.byteorder != "little":
                    values.byteswap()
                if not all(map(math.isfinite, values)):
                    raise ValueError(f"{name} contains NaN or infinite values")
                checked.add(key)
            if (
                0 not in tensor.shape
                and tensor.offset
                + sum(
                    (size - 1) * step for size, step in zip(tensor.shape, tensor.stride)
                )
                >= numel
            ):
                raise ValueError(f"{name} extends past its storage")
            # DataParallel and torch.compile prefixes; CAESAR strips both on load
            while name.startswith(("module.", "_orig_mod.")):
                name = name.split(".", 1)[1]
            if name in shapes:
                raise ValueError(f"Duplicate parameter {name}")
            shapes[name] = tensor.shape
    except (zipfile.BadZipFile, KeyError, EOFError, pickle.UnpicklingError) as error:
        raise ValueError(f"Checkpoint is not a readable PyTorch archive ({error})")
    except (TypeError, AttributeError, IndexError) as error:
        raise ValueError(f"Checkpoint has an unexpected structure ({error})")
    return shapes


def check_checkpoint(data, reference):
    """A quick 'is this a real CAESAR model' check against the default model."""
    shapes, expected = read_checkpoint(data), read_checkpoint(reference)
    missing = sorted(expected.keys() - shapes.keys())
    extra = sorted(shapes.keys() - expected.keys())
    wrong = sorted(
        k for k in expected.keys() & shapes.keys() if shapes[k] != expected[k]
    )
    if missing or extra or wrong:
        raise ValueError(
            f"Checkpoint does not match the {ARCHITECTURE} network: "
            f"{len(missing)} missing, {len(extra)} unexpected, {len(wrong)} wrong-shape "
            f"parameters (first: {(missing + extra + wrong)[0]})"
        )
    return len(shapes)


def check_pull_request(repo, base, head, author, author_id, repository):
    """Validate the change that merging HEAD into BASE would make; return a summary."""

    def git(*args, text=True):
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, text=text
        ).stdout

    if not re.fullmatch(LOGIN, author) or type(author_id) is not int or author_id <= 0:
        raise ValueError("Invalid pull request author")
    merged = subprocess.run(
        ["git", "-C", str(repo), "merge-tree", "--write-tree", base, head],
        capture_output=True,
        text=True,
    )
    if merged.returncode:
        if merged.returncode == 1:
            raise ValueError(
                "The pull request conflicts with the current database; "
                "rerun register_model.py to rebuild it"
            )
        raise ValueError(
            "git merge-tree failed (Git 2.38 or newer is required): "
            + merged.stderr.strip()
        )
    tree = merged.stdout.split()[0]
    changes = {}
    for line in git(
        "diff-tree", "-r", "--no-renames", "--name-status", base, tree
    ).splitlines():
        status, path = line.split("\t", 1)
        changes[path] = status
    old = json.loads(git("show", f"{base}:model_catalog.json"))
    new = json.loads(git("show", f"{tree}:model_catalog.json"))
    admins = admin_ids(json.loads(git("show", f"{base}:registry_policy.json")))
    validate_catalog(new)
    old_names = {m["name"] for m in old["models"]}
    new_names = {m["name"] for m in new["models"]}
    added, removed = new_names - old_names, old_names - new_names

    if len(added) == 1 and not removed:
        (name,) = added
        model = next(m for m in new["models"] if m["name"] == name)
        if set(model) != MODEL_KEYS:
            raise ValueError("Registration has missing or unexpected catalog fields")
        if model["owner"] != author or model["owner_id"] != author_id:
            raise ValueError(
                f"Owner must be the pull request author {author} ({author_id})"
            )
        commit = re.fullmatch(
            rf"https://raw\.githubusercontent\.com/{re.escape(repository)}"
            rf"/([0-9a-f]{{40}})/{re.escape(model['filename'])}",
            model["url"],
        )
        if not commit:
            raise ValueError(
                f"URL must be https://raw.githubusercontent.com/{repository}"
                f"/<commit adding the file>/{model['filename']}"
            )
        expected = register(
            old,
            **{
                k: model[k]
                for k in MODEL_KEYS - {"registration_id", "id", "architecture"}
            },
        )
        if new != expected:
            raise ValueError(
                "Catalog may only append the new model, with the next registration "
                f"number ({expected['models'][-1]['registration_id']})"
            )
        allowed = {"model_catalog.json", "README.md", model["filename"]}
        if changes.get(model["filename"]) != "A":
            raise ValueError(f"The pull request must add {model['filename']}")
        if subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor", commit[1], head],
            capture_output=True,
        ).returncode:
            raise ValueError(
                "The checkpoint URL must name a commit in this pull request"
            )
        data = git("show", f"{tree}:{model['filename']}", text=False)
        pinned = subprocess.run(
            ["git", "-C", str(repo), "show", f"{commit[1]}:{model['filename']}"],
            capture_output=True,
        )
        if pinned.returncode or pinned.stdout != data:
            raise ValueError("The URL must name the commit that adds the checkpoint")
        if hashlib.sha256(data).hexdigest() != model["sha256"]:
            raise ValueError("Checkpoint SHA-256 does not match the catalog")
        default = next(m for m in old["models"] if m["name"] == old["default_model"])
        tensors = check_checkpoint(
            data, git("show", f"{base}:{default['filename']}", text=False)
        )
        summary = (
            f"register {name} as {model['id']} for {author}: "
            f"{len(data):,} bytes, {tensors} float32 tensors matching {default['name']}"
        )
    elif len(removed) == 1 and not added:
        (name,) = removed
        model = next(m for m in old["models"] if m["name"] == name)
        admin = author_id in admins
        if not admin and model["owner_id"] != author_id:
            raise ValueError("Only the model owner or an administrator may retire it")
        replacement = new["default_model"]
        if replacement != old["default_model"] and not admin:
            raise ValueError("Only an administrator may change the default model")
        if new != retire(
            old, name, replacement if replacement != old["default_model"] else None
        ):
            raise ValueError("Retirement may only move the model to retired_models")
        allowed = {"model_catalog.json", "README.md"}
        summary = f"retire {name} for {author}"
    else:
        raise ValueError("A pull request must register or retire exactly one model")

    if set(changes) - allowed:
        raise ValueError(
            "Registration pull requests may only change model_catalog.json and "
            f"README.md and add the checkpoint; also changed: {sorted(set(changes) - allowed)}"
        )
    readme = render_readme(new, git("show", f"{base}:README.md"))
    if git("show", f"{tree}:README.md") != readme:
        raise ValueError("README model list does not match the catalog")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", default=".", help="UFL_MODELS git checkout")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--author-id", type=int, required=True)
    parser.add_argument(
        "--repository", required=True, help="OWNER/REPO of the database"
    )
    args = parser.parse_args()
    try:
        summary = check_pull_request(
            args.repo,
            args.base,
            args.head,
            args.author,
            args.author_id,
            args.repository,
        )
    except (ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(f"Rejected: {error}")
        raise SystemExit(1)
    print(f"Accepted: {summary}")


if __name__ == "__main__":
    main()
