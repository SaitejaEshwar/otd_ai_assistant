"""Download pinned, hash-verified official Windows CPU runtime and local model."""
import hashlib
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_URL = "https://github.com/ggml-org/llama.cpp/releases/download/b11331/llama-b11331-bin-win-cpu-x64.zip"
RUNTIME_SHA = "a10612b76437510a79c8c8ac1734a05fe0ab3833874c2f0a9cab6366ea1c5199"
MODEL_URL = "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/91cad51170dc346986eccefdc2dd33a9da36ead9/qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_SHA = "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(url, path, expected):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and digest(path) == expected:
        print(f"Verified existing {path.name}", flush=True)
        return
    temporary = path.with_suffix(path.suffix + ".part")
    print(f"Downloading {path.name}", flush=True)
    with urllib.request.urlopen(url, timeout=120) as source, temporary.open("wb") as target:
        while chunk := source.read(1024 * 1024):
            target.write(chunk)
    if digest(temporary) != expected:
        raise RuntimeError(f"Hash mismatch for {path.name}; partial file was not installed")
    temporary.replace(path)


def main():
    archive = ROOT / "runtime" / "llama-b11331-win-cpu-x64.zip"
    download(RUNTIME_URL, archive, RUNTIME_SHA)
    output = ROOT / "runtime" / "llama"
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            if not (output / member.filename).resolve().is_relative_to(output.resolve()):
                raise RuntimeError("Archive contains an unsafe path")
        bundle.extractall(output)
    download(MODEL_URL, ROOT / "models" / "qwen2.5-1.5b-instruct-q4_k_m.gguf", MODEL_SHA)
    print("Offline AI installed. Run scripts/start-ai.ps1", flush=True)


if __name__ == "__main__":
    main()
