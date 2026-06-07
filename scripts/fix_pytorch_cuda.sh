#!/usr/bin/env bash
# Fix "NVIDIA driver too old" when pip installed torch+cu130 but driver is CUDA 12.4
set -euo pipefail
PIP="${PIP:-/mnt/data0/parth/ai_ed/ai_ed/bin/pip}"
echo "Installing PyTorch for CUDA 12.4 (cu124)..."
"$PIP" install torch torchvision --index-url https://download.pytorch.org/whl/cu124
python -c "import torch; assert torch.cuda.is_available(), 'CUDA still broken'; print('OK:', torch.__version__, torch.cuda.get_device_name(0))"
