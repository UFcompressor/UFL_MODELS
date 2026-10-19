# UFL model registry

UFL_MODELS is the authoritative database for CAESAR model registrations.
Registration code and ownership tests live in [CAESAR](https://github.com/UFcompressor/CAESAR).
The database stores active and retired identities, checkpoint URLs, and owners.
Existing checkpoints stay here; new contributors may host commit-pinned checkpoints
in their own public GitHub repositories.

## Register or retire a model

Use CAESAR's `register_model.py`, after `gh auth login`:

```sh
python3 register_model.py add --name my_model --display-name "My model" \
  --description "Training data and intended use" \
  --repository YOUR_LOGIN/checkpoints --revision FULL_COMMIT_SHA \
  --checkpoint /path/to/my_model.pt --min-dims 3 --max-dims 5
python3 register_model.py remove my_model
```

Commands open issues in this repository. The trusted workflow validates submissions,
assigns unused registration numbers, commits the catalog and model list automatically,
and records ownership from the authenticated issue author's numeric GitHub ID.
Users can retire only their own models; E53klasky (ID 173562962) is the initial
administrator and can register or retire any model. Only an administrator may
change the default using `remove NAME --default-model REPLACEMENT`.

Retirement preserves checkpoint files and identities. Numbers, names, hashes, and
filenames remain reserved. Requests cannot rewrite or revive retired registrations.
Ordinary contributors need issue access, not repository write access. Direct write
access to the catalog or workflow bypasses this service; keep it restricted to
trusted administrators and automation.

The compatibility `register_model.py` here forwards to an adjacent CAESAR checkout.
It contains no registration logic. See
[CAESAR's setup and usage guide](https://github.com/UFcompressor/CAESAR/blob/main/docs/model_registration.md)
for activation, pinned code revisions, automatic commit permissions, validation
limits, retries, and synchronizing CAESAR's release snapshot. The workflow is not
active until an administrator sets `CAESAR_REGISTRY_REF` to a reviewed CAESAR commit.

## Database checks

```sh
python3 ../CAESAR/register_model.py check --database .
python3 -m unittest discover -s test -v
```

Model byte hashes and strict network compatibility are checked during CAESAR download
and compilation. Registration checks public checkpoint hashes without executing
checkpoint code. Hosting must remain available for future downloads.

<!-- BEGIN GENERATED MODEL LIST -->

| Registration | Model | Owner | Status | Checkpoint | Dimensions | Description |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | CAESAR v1 (caesar_v1) | E53klasky | Active | caesar_v.pt | 3D–5D | Foundation model, original CAESAR v1 release; trained for scientific data with 3D–5D inputs. |
| 2 | CAESAR v2 (caesar_v2) | E53klasky | Active (default) | model_bs64_ep100k.pt | 3D–5D | Foundation model, optimized CAESAR v2 release; trained for scientific data with 3D–5D inputs. |
| 3 | eelsM1 (eelsM1) | E53klasky | Active | eelsM1.pt | 3D–5D | Domain fine-tune of the CAESAR foundation model for EELS; trained and tested on one EELS dataset, with 3D–5D inputs. |
| 4 | microscopy (microscopy) | E53klasky | Active | microscopy.pt | 3D–5D | Domain-specific microscopy model; trained and tested across four microscopy datasets, with 3D–5D inputs. |
| 5 | Xcompact3d latent 16x16 (Xcompact3d_latent_16_16) | E53klasky | Active | Xcompact3d_latent_16_16.pt | 3D–5D | Xcompact3d checkpoint; document training data and intended use |

<!-- END GENERATED MODEL LIST -->
