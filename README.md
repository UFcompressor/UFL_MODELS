# UFL model registry

`model_catalog.json` is the authoritative registration catalog for CAESAR checkpoints.
Every checkpoint must be registered before it can be compiled with CAESAR.

<!-- BEGIN GENERATED MODEL LIST -->

| Registration | Model | Status | Checkpoint | Dimensions | Description |
| --- | --- | --- | --- | --- | --- |
| 1 | CAESAR v1 (caesar_v1) | Active | caesar_v.pt | 3D–5D | Foundation model, original CAESAR v1 release; trained for scientific data with 3D–5D inputs. |
| 2 | CAESAR v2 (caesar_v2) | Active (default) | model_bs64_ep100k.pt | 3D–5D | Foundation model, optimized CAESAR v2 release; trained for scientific data with 3D–5D inputs. |
| 3 | eelsM1 (eelsM1) | Active | eelsM1.pt | 3D–5D | Domain fine-tune of the CAESAR foundation model for EELS; trained and tested on one EELS dataset, with 3D–5D inputs. |
| 4 | microscopy (microscopy) | Active | microscopy.pt | 3D–5D | Domain-specific microscopy model; trained and tested across four microscopy datasets, with 3D–5D inputs. |
| 5 | Xcompact3d latent 16x16 (Xcompact3d_latent_16_16) | Active | Xcompact3d_latent_16_16.pt | 3D–5D | Xcompact3d checkpoint; document training data and intended use |

<!-- END GENERATED MODEL LIST -->

## Registering a checkpoint

Registration is a reviewed catalog change in this repository, not a local compile option.
Assign a new positive `registration_id` that has never been used. Never reuse or
change an existing number, including when replacing or retiring a checkpoint.
Names, registration numbers, checkpoint hashes, and full identities must be unique.
A changed checkpoint requires a new registration. Preserve existing registrations
so older compressed data can still identify and obtain its required checkpoint.

Each entry records `name`, `display_name`, `description`, `registration_id`,
`sha256`, `id`, `filename`, immutable HTTPS `url`, `architecture`, `min_dims`, and
`max_dims`. Compute SHA-256 over the exact checkpoint bytes; the identity is
`ufl:<registration_id>@sha256:<64 lowercase hex digits>`. The device is not part
of checkpoint identity; it belongs to the compiled installation.

Use a commit-pinned download URL once the checkpoint has been committed. The
current architecture identifier is `caesar-bcrn-v1`. Supported input ranks are
2D–5D through CAESAR's internal preparation; this does not mean arbitrary tensor
shapes can be passed directly to the exported network.

After a catalog change is approved, synchronize CAESAR's `model_catalog.json`
snapshot. CAESAR independently checks that snapshot during compilation and
rejects unregistered checkpoints, altered selections, and hash mismatches.
Validate the synchronized catalog with `python model_registry.py --list` in
CAESAR, and run its registry tests. The snapshot makes released CAESAR versions
reproducible without fetching mutable metadata during compilation.

This is repository-controlled registration, not cryptographic licensing:
someone modifying CAESAR or its bundled catalog can modify the checks as well.

## Registration commands

Validate all catalog entries and local checkpoint hashes:

```sh
python3 register_model.py --check
```

After committing a new checkpoint, prepare its registration (the number defaults
to the next unused number):

```sh
python3 register_model.py --name new_model --display-name "New model" \
  --description "Describe its intended data and training provenance" \
  --checkpoint new_model.pt --revision <checkpoint-commit-sha>
```

Review and publish that catalog change, then synchronize the CAESAR snapshot.
To check that a change preserves prior identities, export the previous catalog
and run `python3 register_model.py --check --previous previous_catalog.json`.
Concurrent registration branches must resolve number collisions before merging;
validation rejects duplicate numbers rather than silently renumbering entries.

## Registering Xcompact3d

The checkpoint is a named option, not a positional argument. Commit and push the
checkpoint to UFL_MODELS first, then use that exact commit:

```sh
git add Xcompact3d_latent_16_16.pt
git commit -m "Add Xcompact3d latent 16 checkpoint"
checkpoint_revision=$(git rev-parse HEAD)
git push origin HEAD
python3 register_model.py \
  --name Xcompact3d_latent_16_16 \
  --display-name "Xcompact3d latent 16x16" \
  --description "Xcompact3d checkpoint; document training data and intended use" \
  --checkpoint Xcompact3d_latent_16_16.pt \
  --revision "$checkpoint_revision" \
  --min-dims 3 --max-dims 5
python3 register_model.py --check
```

Use the actual supported ranks and training description for your checkpoint.
Registration verifies that the local file exactly matches the Git blob at the
pinned commit. Untracked files, uncommitted changes, and files absent from that
commit are rejected. This is local Git verification; the script does not verify
that a commit was pushed or is accessible publicly. Push it before publishing the
catalog so its GitHub URL can be downloaded. GitHub remains the checkpoint host.

## Deleting a registration

```sh
python3 register_model.py --delete Xcompact3d_latent_16_16
```

Deletion removes the model from the active `models` list and moves its full entry
to `retired_models`. Its number, name, filename, hash, and identity stay reserved.
The checkpoint file and Git history are preserved. This lets historical catalog
snapshots keep referring to the original checkpoint. Retired models cannot be
reactivated. Register a changed checkpoint under a new identity.

To delete the current default, explicitly select another active model:

```sh
python3 register_model.py --delete caesar_v2 --default-model caesar_v1
```

Review and publish the catalog change and synchronize CAESAR's snapshot after
either registration or deletion. Existing CAESAR releases retain their bundled
catalog; a synchronized catalog will no longer select or compile a retired model.
The `--previous` check requires all old records to remain either active or retired,
and rejects changes to their immutable fields or reactivation of retired records.
Run lifecycle tests with `python3 -m unittest discover -s test -v`.


## Maintaining the registry

UFL_MODELS is currently the model database: `model_catalog.json` stores the records,
this repository stores the checkpoints, and this README displays the catalog.
Registering a model adds its row automatically; `--delete NAME` marks it retired.
The default model is labeled explicitly. Edit catalog metadata in the JSON and run
`python3 register_model.py --update-readme` to refresh the generated list. Text
outside the generated markers is preserved. `--check` also detects a stale list.

Contributors with repository write access can add or retire models, then commit
and push both `model_catalog.json` and `README.md` together. Contributors without
write access can submit these changes through a pull request. GitHub repository
permissions and review govern publishing; the script does not enforce ownership
by checkpoint author. Retirement preserves checkpoint files and reserves identities.

CAESAR consumes a catalog snapshot from UFL_MODELS. A future repository merge or
external database can change where records are stored while preserving model
identities. For now, maintain the catalog and generated model list here.
