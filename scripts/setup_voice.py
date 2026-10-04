"""Install the pinned Windows CPU speech runtime and English model."""
import zipfile
from setup_ai import ROOT, download

def main():
    archive = ROOT / 'runtime' / 'whisper-v1.8.2-x64.zip'
    download('https://github.com/ggml-org/whisper.cpp/releases/download/v1.8.2/whisper-bin-x64.zip', archive,
             'b1514ebc099765e39fa37eb780b92a140a94c86bb0b3b3d98226b38825979732')
    output = ROOT / 'runtime' / 'whisper'
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            if not (output / member.filename).resolve().is_relative_to(output.resolve()):
                raise RuntimeError('Unsafe archive path')
        bundle.extractall(output)
    download('https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin',
             ROOT / 'models' / 'ggml-base.en.bin',
             'a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002')
    print('Voice installed. Restart the desk service. No separate voice server is needed.')

if __name__ == '__main__': main()
