"""Windows-friendly AI installation diagnostics (no API keys, no user images)."""
from __future__ import annotations
import argparse
import importlib.metadata
import platform
import sys
import traceback
from .recognition import local_ai_missing, test_local_model


def check_environment(test_model=False):
    print('Guia Lanka Photo Manager - AI diagnostics v0.1.2', flush=True)
    print('Python:', sys.version.split()[0], '|', platform.platform(), flush=True)
    print('Executable:', sys.executable, flush=True)
    for package in ('torch', 'torchvision', 'open-clip-torch'):
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            version = 'NOT INSTALLED'
        print(f'{package}: {version}', flush=True)
    missing = local_ai_missing()
    if missing:
        print('\nFAIL: Missing ' + ', '.join(missing), flush=True)
        print('SOLUTION: Run INSTALL_AI_WINDOWS.bat, then run this diagnostic again.', flush=True)
        return False
    try:
        print('Checking PyTorch and torchvision imports...', flush=True)
        import torch
        import torchvision
        print('PyTorch imported. Device: CPU; CUDA support available: ' + str(torch.cuda.is_available()), flush=True)
        print('Checking OpenCLIP import...', flush=True)
        import open_clip
        print('OpenCLIP imported successfully.', flush=True)
        if test_model:
            print('Testing pretrained model. First use may download model weights...', flush=True)
            print(test_local_model(print), flush=True)
        else:
            print('AI libraries are installed. For a full model test, run DIAGNOSE_AI_WINDOWS.bat.', flush=True)
        return True
    except Exception as exc:
        print(f'\nFAIL: {type(exc).__name__}: {exc}', flush=True)
        traceback.print_exc()
        print('\nTry INSTALL_AI_WINDOWS.bat again. If this fails, provide the diagnostic output.', flush=True)
        return False


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', action='store_true', help='Download / load AI model and classify a test image')
    args = parser.parse_args(argv)
    return 0 if check_environment(test_model=args.model) else 1


if __name__ == '__main__':
    raise SystemExit(main())
