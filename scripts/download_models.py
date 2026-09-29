"""Provision the pinned face models during setup; the application stays offline."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen


MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        "f12e12798e8314f7c074a6656816c048dcc95b7a",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        "face_detection_yunet",
    ),
    "face_recognition_sface_2021dec.onnx": (
        "ba91a3b91d00d76e86540d4013f944bd6b514e39",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
        "face_recognition_sface",
    ),
}


class ModelDownloadError(RuntimeError):
    """Raised when a model cannot be downloaded or fails its pinned checksum."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_models(model_dir: str | Path) -> list[Path]:
    """Download missing models from pinned OpenCV Zoo commits and verify each hash."""
    destination = Path(model_dir).expanduser().resolve()
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ModelDownloadError(f"Cannot create model directory '{destination}': {exc}") from exc

    paths = []
    for filename, (commit, expected_hash, model_folder) in MODELS.items():
        target = destination / filename
        if target.exists():
            actual_hash = sha256_file(target)
            if actual_hash != expected_hash:
                raise ModelDownloadError(
                    f"Existing model '{target}' has SHA-256 {actual_hash}; "
                    f"expected {expected_hash}. Move it aside and run setup again."
                )
            paths.append(target)
            continue

        url = (
            "https://media.githubusercontent.com/media/opencv/opencv_zoo/"
            f"{commit}/models/{model_folder}/{filename}"
        )
        request = Request(url, headers={"User-Agent": "face-attendance-model-setup"})
        temporary_name = None
        try:
            with urlopen(request, timeout=120) as response:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=destination,
                    prefix=f".{filename}.",
                    suffix=".part",
                    delete=False,
                ) as temporary_file:
                    temporary_name = temporary_file.name
                    digest = hashlib.sha256()
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        temporary_file.write(chunk)
                        digest.update(chunk)
            actual_hash = digest.hexdigest()
            if actual_hash != expected_hash:
                raise ModelDownloadError(
                    f"Downloaded '{filename}' has SHA-256 {actual_hash}; "
                    f"expected {expected_hash}."
                )
            os.replace(temporary_name, target)
            temporary_name = None
            paths.append(target)
        except ModelDownloadError:
            raise
        except Exception as exc:
            raise ModelDownloadError(f"Could not download '{filename}': {exc}") from exc
        finally:
            if temporary_name:
                try:
                    Path(temporary_name).unlink()
                except OSError:
                    pass
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "models",
        help="directory to hold locally provisioned ONNX models",
    )
    args = parser.parse_args()
    try:
        for path in ensure_models(args.model_dir):
            print(f"Verified {path} (SHA-256 {sha256_file(path)})")
    except ModelDownloadError as exc:
        parser.exit(1, f"Model setup failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
