# Targeted recognition fixes: repository integration

This development branch imports the inference code evaluated in the local
`targeted-retrain-code-20260914-v1/comparison-code` snapshot. It does not select
or deploy the experimental recognition checkpoint.

## Scope

- Preserve observed partial date fields, with explicit negative role evidence
  still allowed to retract an incorrect output.
- Separate a lot-number prefix only with a nearby printed lot/date legend;
  connect split manufacturing-date labels and retain non-expiry roles across
  recovery passes mapped to the original region.
- Carry the evaluated base-first recovery implementation and its dependencies,
  including recognizer padding-frame masking, exact crop caching, width batches,
  and shared recognition. Optional candidate/policy diagnostics remain opt-in.
- Regenerate the self-contained `predict.ipynb` from the same source modules.

The evaluated inference snapshot depends on earlier workspace-only changes;
importing only `date_extraction.py` would leave missing dependencies. Existing
repository workflow, approval, CPU allocation and training scripts are retained.
The unused packaging-augmentation experiment and its augmentation-specific test
module are not imported. No augmentation is enabled by this integration.

## Verification

Run the repository tests without starting a full OCR evaluation or training:

```powershell
$env:PYTHONPATH = 'notebooks/project'
.\.labeling_paddle_env\Scripts\python.exe -B -m unittest discover -s notebooks/project/tests -t notebooks/project
```

To regenerate the notebook, generate a new file first (the generator refuses to
overwrite an existing output), review it, then replace the tracked notebook:

```powershell
.\.labeling_paddle_env\Scripts\python.exe notebooks/project/scripts/build_embedded_notebook.py --code-root . --output predict.generated.ipynb
Move-Item -LiteralPath predict.generated.ipynb -Destination predict.ipynb -Force
```

`notebooks/project/.gitattributes` fixes inference-source and generator line
endings to LF so a Windows checkout does not invalidate the embedded byte-hash manifest.
Line-ending normalization does not change the evaluated Python syntax trees.

The integration passed 566 repository tests. This is software verification,
not an additional full-image accuracy or timing measurement. Prior full-image
results remain in the local execution workspace and are not rewritten here.

## Exclusions

No original images, gold workbook, crop annotations, approval records, training
data/configuration, candidate checkpoints, inference bundles, or run outputs
are copied into this commit. Shared weights, formal round completion, and the
decision to adopt a model are unchanged. This development branch is not an
automatic promotion to `main` or a restart of training/evaluation.
