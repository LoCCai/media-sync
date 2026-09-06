"""Read-only comparison of packaged application sources against this checkout."""

from __future__ import annotations

import hashlib
import json
import sys
import tarfile
import zipfile
from pathlib import Path

repository = Path(__file__).resolve().parents[4]
package_root = Path(sys.argv[1]).resolve(strict=True)
sources = {
    path.relative_to(repository / "src").as_posix(): path.read_bytes()
    for path in (repository / "src" / "media_sync").rglob("*.py")
}
results = []
for package in sorted(package_root.iterdir()):
    if package.name.endswith(".whl"):
        with zipfile.ZipFile(package) as wheel:
            observed = {
                name: wheel.read(name)
                for name in wheel.namelist()
                if name.startswith("media_sync/") and name.endswith(".py")
            }
    elif package.name.endswith(".tar.gz"):
        with tarfile.open(package, "r:gz") as sdist:
            observed = {}
            for member in sdist.getmembers():
                if not member.isfile() or "/src/media_sync/" not in member.name or not member.name.endswith(".py"):
                    continue
                stream = sdist.extractfile(member)
                assert stream is not None
                observed["media_sync/" + member.name.split("/src/media_sync/", 1)[1]] = stream.read()
    else:
        continue
    assert observed == sources, f"Application source mismatch: {package.name}"
    results.append(
        {
            "package": package.name,
            "application_python_files": len(observed),
            "source_bytes_equal": True,
            "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        }
    )
assert len(results) == 2
print(json.dumps(results, indent=2))
