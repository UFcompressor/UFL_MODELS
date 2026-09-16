# UFL model registry

`model_catalog.json` is the authoritative registration catalog for CAESAR checkpoints.
Every checkpoint must be registered before it can be compiled with CAESAR.

| Registration | Model | Checkpoint | Description |
| --- | --- | --- | --- |
| 1 | CAESAR v1 (`caesar_v1`) | `caesar_v.pt` | Foundation model, original CAESAR v1 release; trained for scientific data with 3D–5D inputs. |
| 2 | CAESAR v2 (`caesar_v2`) | `model_bs64_ep100k.pt` | Foundation model, optimized CAESAR v2 release; trained for scientific data with 3D–5D inputs. |
| 3 | `eelsM1` | `eelsM1.pt` | Domain fine-tune of the CAESAR foundation model for EELS; trained and tested on one EELS dataset; supports 3D–5D inputs. |
| 4 | `microscopy` | `microscopy.pt` | Domain-specific microscopy model; trained and tested across four microscopy datasets; supports 3D–5D inputs. |

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
