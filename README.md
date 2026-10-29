# UFL model registry

UFL_MODELS is the authoritative database for CAESAR model registrations. It stores
registered checkpoints, their active and retired identities, URLs and owners.
The registration client lives in [CAESAR](https://github.com/UFcompressor/CAESAR);
the checks the workflow runs live here in `test/check_registration.py`.

## Register or retire a model

Use CAESAR's `register_model.py`, after `gh auth login`:

```sh
python3 register_model.py add --name my_model --display-name "My model" \
  --description "Training data and intended use" \
  --checkpoint /path/to/my_model.pt --min-dims 3 --max-dims 5
python3 register_model.py remove my_model
```

Each command opens a `[model-registry]` pull request from your fork. `add` commits
the checkpoint and its catalog entry; `remove` moves your entry to `retired_models`.
The workflow (`.github/workflows/model-registry.yml`) checks the pull request with
`test/check_registration.py` from this repository, never with code from the pull
request, and merges it when every check passes; otherwise it comments the reason.
It checks that:

- exactly one model is registered or retired and nothing else changed;
- the owner is the pull request author's login and numeric GitHub ID, and the
  registration number is the next unused one; names, files, hashes and numbers
  are unique among active and retired models;
- the checkpoint is a real CAESAR model: a PyTorch state_dict of finite float32
  tensors with the default model's parameter names and shapes, within 5% of its
  size. It is read as data by a restricted unpickler and never executed;
- the URL names the pull request commit that adds the checkpoint, the SHA-256
  matches, and the README model list matches the catalog.

Users can retire only their own models; E53klasky (ID 173562962) is the initial
administrator and can retire any model. Only an administrator may change the
default using `remove NAME --default-model REPLACEMENT`. Retirement preserves
checkpoint files and identities; numbers, names, hashes and filenames remain
reserved. Contributors need no write access. Direct write access to the catalog,
checks or workflow bypasses this service; keep it restricted to administrators.
The workflow merges with merge commits, so keep merge commits allowed.

The compatibility `register_model.py` here forwards to an adjacent CAESAR checkout.
See [CAESAR's registration guide](https://github.com/UFcompressor/CAESAR/blob/master/docs/model_registration.md)
for repository settings, testing the workflow, and synchronizing CAESAR's release
snapshot.

## Database checks

```sh
python3 ../CAESAR/register_model.py check --database .
python3 -m unittest discover -s test -v
```

<!-- BEGIN GENERATED MODEL LIST -->

| Registration | Model | Owner | Status | Checkpoint | Dimensions | Description |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | CAESAR v1 (caesar_v1) | E53klasky | Active | caesar_v.pt | 3D–5D | Foundation model, original CAESAR v1 release; trained for scientific data with 3D–5D inputs. |
| 2 | CAESAR v2 (caesar_v2) | E53klasky | Active (default) | model_bs64_ep100k.pt | 3D–5D | Foundation model, optimized CAESAR v2 release; trained for scientific data with 3D–5D inputs. |
| 3 | eelsM1 (eelsM1) | E53klasky | Active | eelsM1.pt | 3D–5D | Domain fine-tune of the CAESAR foundation model for EELS; trained and tested on one EELS dataset, with 3D–5D inputs. |
| 4 | microscopy (microscopy) | E53klasky | Active | microscopy.pt | 3D–5D | Domain-specific microscopy model; trained and tested across four microscopy datasets, with 3D–5D inputs. |
| 5 | Xcompact3d latent 16x16 (Xcompact3d_latent_16_16) | E53klasky | Active | Xcompact3d_latent_16_16.pt | 3D–5D | Xcompact3d checkpoint; document training data and intended use |
| 6 | rahul_isabel_tc_v1 (workflow test) (rahul_isabel_tc_v1) | arsenious | Active | rahul_isabel_tc_v1.pt | 3D–5D | Workflow test, not for production. caesar_v2 fine-tuned 3k steps on Hurricane Isabel TCf48 frames 0-79; held-out NRMSE 0.00623. |

<!-- END GENERATED MODEL LIST -->
