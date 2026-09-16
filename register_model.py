"""Register a checkpoint in the UFL catalog, or validate existing registrations."""

import argparse
import hashlib
import json
from pathlib import Path
import re


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def validate(catalog, root, previous=None):
    if catalog["schema_version"] != 1:
        raise ValueError("Unsupported catalog schema")
    seen = {
        key: set() for key in ("registration_id", "name", "id", "sha256", "filename")
    }
    for model in catalog["models"]:
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
        if model["sha256"] != digest(root / model["filename"]):
            raise ValueError(f"Checkpoint hash mismatch: {model['name']}")
        if model["id"] != f"ufl:{model['registration_id']}@sha256:{model['sha256']}":
            raise ValueError("Identity does not match registration number and hash")
    if catalog["default_model"] not in seen["name"]:
        raise ValueError("Default model is unregistered")
    if previous:
        current = {m["registration_id"]: m for m in catalog["models"]}
        for old in previous["models"]:
            new = current.get(old["registration_id"])
            if new is None:
                raise ValueError("Existing registrations cannot be removed")
            for key in old:
                if key not in ("description", "display_name") and new[key] != old[key]:
                    raise ValueError(
                        f"Existing registration {old['registration_id']} cannot change {key}"
                    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog", type=Path, default=Path(__file__).with_name("model_catalog.json")
    )
    parser.add_argument("--check", action="store_true")
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
    if args.check:
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
        else max(m["registration_id"] for m in catalog["models"]) + 1
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
    args.catalog.write_text(json.dumps(catalog, indent=2) + "\n")
    print(f"Registered {model['id']}. Review this catalog change before publishing.")


if __name__ == "__main__":
    main()
