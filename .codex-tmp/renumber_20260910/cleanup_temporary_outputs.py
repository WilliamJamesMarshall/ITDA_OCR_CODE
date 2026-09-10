from pathlib import Path


workspace = Path(r"C:\ITDA_OCR_CODE").resolve()
output = (workspace / "outputs" / "01a08828-ff4d-7401-bdfe-75041206f3e4" / "renumbered_labels").resolve()

if workspace not in output.parents:
    raise RuntimeError(f"Unsafe output path: {output}")

removed_files = 0
if output.exists():
    for file_path in sorted((path for path in output.rglob("*") if path.is_file()), reverse=True):
        if output not in file_path.resolve().parents:
            raise RuntimeError(f"Unsafe file path: {file_path}")
        file_path.unlink()
        removed_files += 1
    for directory in sorted((path for path in output.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
        directory.rmdir()
    output.rmdir()

removed_caches = 0
labels = (workspace / "labels").resolve()
for cache in sorted(labels.rglob("__pycache__"), key=lambda path: len(path.parts), reverse=True):
    if "node_modules" in cache.parts:
        continue
    if labels not in cache.resolve().parents:
        raise RuntimeError(f"Unsafe cache path: {cache}")
    for file_path in cache.iterdir():
        if file_path.is_file():
            file_path.unlink()
    cache.rmdir()
    removed_caches += 1

print({"removed_output_files": removed_files, "removed_pycache_dirs": removed_caches})
