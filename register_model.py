"""Register a checkpoint in the UFL catalog, or validate existing registrations."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def verify_committed_checkpoint(root, model):
    """Verify the pinned Git blob, without loading large checkpoints into memory."""
    revision = model["url"].split("/")[-2]
    try:
        top = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"], text=True
        ).strip()
        if Path(top).resolve() != Path(root).resolve():
            raise ValueError("The catalog must be at the repository root")
        subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", revision + "^{commit}"],
            check=True, capture_output=True,
        )
        with subprocess.Popen(
            ["git", "-C", str(root), "cat-file", "blob", revision + ":" + model["filename"]],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ) as process:
            value = hashlib.sha256()
            for block in iter(lambda: process.stdout.read(1024 * 1024), b""):
                value.update(block)
            error = process.stderr.read().decode(errors="replace")
            if process.wait():
                raise ValueError("Checkpoint is not committed at the pinned revision: " + error.strip())
        if value.hexdigest() != model["sha256"]:
            raise ValueError(f"Committed checkpoint hash mismatch: {model['name']}")
    except subprocess.CalledProcessError as error:
        raise ValueError("Checkpoint revision must be an existing local Git commit") from error


def validate(catalog, root, previous=None):
    if catalog["schema_version"] != 1:
        raise ValueError("Unsupported catalog schema")
    seen = {
        key: set() for key in ("registration_id", "name", "id", "sha256", "filename")
    }
    for model in catalog["models"] + catalog.get("retired_models", []):
        for key, values in seen.items():
            if model[key] in values:
                raise ValueError(f"Duplicate {key}: {model[key]}")
            values.add(model[key])
        if type(model["registration_id"]) is not int or model["registration_id"] <= 0:
            raise ValueError("Registration numbers must be positive integers")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", model["name"]):
            raise ValueError("Invalid model name")
        if not re.fullmatch(r"[A-Za-z0-9_-]+\.pt", model["filename"]):
            raise ValueError("Invalid checkpoint filename")
        if not (
            type(model["min_dims"]) is int
            and type(model["max_dims"]) is int
            and 2 <= model["min_dims"] <= model["max_dims"] <= 5
        ):
            raise ValueError("Invalid supported dimensions")
        if model["architecture"] != "caesar-bcrn-v1":
            raise ValueError("Architecture needs CAESAR implementation support first")
        if not model["description"] or not model["display_name"]:
            raise ValueError("Display name and description are required")
        if not re.fullmatch(
            r"https://raw\.githubusercontent\.com/UFcompressor/UFL_MODELS/[0-9a-f]{40}/"
            + re.escape(model["filename"]),
            model["url"],
        ):
            raise ValueError("Use an immutable UFL_MODELS commit URL")
        if model in catalog["models"]:
            if model["sha256"] != digest(root / model["filename"]):
                raise ValueError(f"Checkpoint hash mismatch: {model['name']}")
            verify_committed_checkpoint(root, model)
        if model["id"] != f"ufl:{model['registration_id']}@sha256:{model['sha256']}":
            raise ValueError("Identity does not match registration number and hash")
    if catalog["default_model"] not in {m["name"] for m in catalog["models"]}:
        raise ValueError("Default model is unregistered")
    if previous:
        current = {
            m["registration_id"]: m
            for m in catalog["models"] + catalog.get("retired_models", [])
        }
        active = {m["registration_id"] for m in catalog["models"]}
        if any(m["registration_id"] in active for m in previous.get("retired_models", [])):
            raise ValueError("Retired registrations cannot be reactivated")
        for old in previous["models"] + previous.get("retired_models", []):
            new = current.get(old["registration_id"])
            if new is None:
                raise ValueError("Existing registrations cannot be removed")
            for key in old:
                if key not in ("description", "display_name") and new[key] != old[key]:
                    raise ValueError(
                        f"Existing registration {old['registration_id']} cannot change {key}"
                    )


README_START = "<!-- BEGIN GENERATED MODEL LIST -->"
README_END = "<!-- END GENERATED MODEL LIST -->"


def model_list(catalog):
    """Render the public list from the authoritative catalog."""
    import html

    def cell(value):
        return html.escape(str(value), quote=False).replace("|", "&#124;").replace("\n", " ").replace("\r", " ")

    lines = [README_START, "", "| Registration | Model | Status | Checkpoint | Dimensions | Description |",
             "| --- | --- | --- | --- | --- | --- |"]
    for status, models in (("Active", catalog["models"]), ("Retired", catalog.get("retired_models", []))):
        for model in sorted(models, key=lambda m: m["registration_id"]):
            state = status
            if status == "Active" and model["name"] == catalog["default_model"]:
                state = "Active (default)"
            values = [model["registration_id"], f"{model['display_name']} ({model['name']})", state,
                      model["filename"], f"{model['min_dims']}D–{model['max_dims']}D", model["description"]]
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
    return text[:start] + block + text[end + len(README_END):]


def save_catalog(path, catalog):
    readme = path.with_name("README.md")
    text = readme.read_text(encoding="utf-8") if readme.exists() else "# UFL model registry\n"
    updated = render_readme(catalog, text)
    path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    readme.write_text(updated, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog", type=Path, default=Path(__file__).with_name("model_catalog.json")
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--update-readme", action="store_true", help="Rebuild the README model list from the catalog")
    actions.add_argument("--delete", metavar="NAME", help="Retire a registration by name; keep its identity reserved")
    parser.add_argument("--default-model", help="Replacement default when deleting the current default")
    parser.add_argument(
        "--previous",
        type=Path,
        help="Previous catalog to enforce immutable registrations",
    )
    parser.add_argument("--name")
    parser.add_argument("--display-name")
    parser.add_argument("--description")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument(
        "--revision", help="40-character commit containing the checkpoint"
    )
    parser.add_argument(
        "--registration-id", type=int, help="Defaults to the next unused number"
    )
    parser.add_argument("--min-dims", type=int, default=2)
    parser.add_argument("--max-dims", type=int, default=5)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text())
    previous = json.loads(args.previous.read_text()) if args.previous else None
    validate(catalog, args.catalog.parent, previous)
    if args.default_model and not args.delete:
        parser.error("--default-model requires --delete")
    if args.delete:
        matches = [m for m in catalog["models"] if m["name"] == args.delete]
        if not matches:
            parser.error(f"No active registration named {args.delete!r}")
        model = matches[0]
        if catalog["default_model"] == args.delete and not args.default_model:
            parser.error("Deleting the default requires --default-model with another active name")
        catalog["models"].remove(model)
        catalog.setdefault("retired_models", []).append(model)
        if args.default_model:
            catalog["default_model"] = args.default_model
        validate(catalog, args.catalog.parent, previous)
        save_catalog(args.catalog, catalog)
        print(f"Retired {model['id']}. Checkpoint files were preserved; its number cannot be reused.")
        return
    if args.update_readme:
        readme = args.catalog.with_name("README.md")
        text = readme.read_text(encoding="utf-8") if readme.exists() else "# UFL model registry\n"
        readme.write_text(render_readme(catalog, text), encoding="utf-8")
        print("Updated README model list")
        return
    if args.check:
        readme = args.catalog.with_name("README.md")
        text = readme.read_text(encoding="utf-8")
        if text != render_readme(catalog, text):
            raise ValueError("README model list is stale; run --update-readme")
        print(f"Validated {len(catalog['models'])} registrations")
        return
    if not all(
        (args.name, args.display_name, args.description, args.checkpoint, args.revision)
    ):
        parser.error(
            "Registration requires --name, --display-name, --description, --checkpoint, and --revision"
        )
    checkpoint = args.checkpoint.resolve()
    if checkpoint.parent != args.catalog.resolve().parent:
        parser.error("The checkpoint must be in the catalog's repository directory")
    number = (
        args.registration_id
        if args.registration_id is not None
        else max((m["registration_id"] for m in catalog["models"] + catalog.get("retired_models", [])), default=0) + 1
    )
    sha = digest(checkpoint)
    model = dict(
        registration_id=number,
        name=args.name,
        display_name=args.display_name,
        description=args.description,
        filename=checkpoint.name,
        sha256=sha,
        id=f"ufl:{number}@sha256:{sha}",
        min_dims=args.min_dims,
        max_dims=args.max_dims,
        architecture="caesar-bcrn-v1",
        url=f"https://raw.githubusercontent.com/UFcompressor/UFL_MODELS/{args.revision}/{checkpoint.name}",
    )
    catalog["models"].append(model)
    validate(catalog, args.catalog.parent, previous)
    save_catalog(args.catalog, catalog)
    print(f"Registered {model['id']}. Review this catalog change before publishing.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        raise SystemExit(f"Error: {error}") from error
