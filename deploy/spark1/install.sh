#!/usr/bin/env bash
# Colophon SAM 3.1 worker on spark1 (DGX Spark, GB10, aarch64, CUDA 13 / sm_121).
# Idempotent. Run ON spark1 as colophon, after copying the worker and unit next to it:
#
#   scp colophon/worker_sam.py deploy/spark1/colophon-worker.service spark1:services/colophon-worker/
#   ssh spark1 bash -s < deploy/spark1/install.sh
#
# Installs nothing system-wide and no sudo. It does NOT enable or start the unit.
set -euo pipefail

SVC="$HOME/services/colophon-worker"
VENV="$SVC/venv"
SRC="$SVC/sam3-src"            # NOT "sam3": that name next to worker_sam.py shadows the package
MODELS="$HOME/models/sam3"
SCRATCH="$HOME/scratch/2026-11-02-colophon"
UV="${UV:-$HOME/.local/bin/uv}"

# The torch recipe works on a DGX Spark (services/toolkit/.venv):
TORCH_INDEX="https://download.pytorch.org/whl/cu130"
TORCH_PKGS=(torch==2.13.0 torchvision==0.28.0)          # -> 2.13.0+cu130 / 0.28.0+cu130, aarch64
SAM3_REPO="https://github.com/facebookresearch/sam3.git"
SAM3_REV="f1647e8d0c1d280991f4d1b7d974c2704537fe66"      # main, 2026-10-23
COMFY_CKPT="$HOME/models/comfyui/checkpoints/sam3.1_multiplex_fp16.safetensors"

mkdir -p "$SVC" "$MODELS" "$SCRATCH"

[ -x "$UV" ] || { echo "uv not found at $UV" >&2; exit 1; }
[ -x "$VENV/bin/python" ] || "$UV" venv --python 3.12 "$VENV"

if ! "$VENV/bin/python" -c 'import torch,sys; sys.exit(0 if torch.__version__.startswith("2.13.0") and torch.cuda.is_available() else 1)' 2>/dev/null; then
  "$UV" pip install --python "$VENV/bin/python" "${TORCH_PKGS[@]}" --index-url "$TORCH_INDEX"
fi

if [ ! -d "$SRC/.git" ]; then
  git clone -q "$SAM3_REPO" "$SRC"
fi
git -C "$SRC" fetch -q origin "$SAM3_REV" 2>/dev/null || true
git -C "$SRC" checkout -q "$SAM3_REV"

# sam3's image path also imports psutil; pycocotools for mask RLE; safetensors for the repack.
"$UV" pip install --python "$VENV/bin/python" -e "$SRC" \
  psutil pycocotools einops safetensors opencv-python-headless

# Weights. The official facebook/sam3.1 checkpoint is gated and the owner's HF account
# (author) was not on the authorized list on 2026-11-02, so the worker loads the
# Comfy-Org repack ComfyUI already keeps on this host (same detector.* / tracker.* keys,
# fp16). A hard link, so ComfyUI's file is untouched and a later ComfyUI library
# reshuffle cannot break the worker.
if [ ! -e "$MODELS/sam3.1_multiplex_fp16.safetensors" ] && [ -e "$COMFY_CKPT" ]; then
  ln "$COMFY_CKPT" "$MODELS/sam3.1_multiplex_fp16.safetensors"
fi
# Once access is granted, fetch the official one (token on stdin only, never as an arg):
#   python3 get-secret hf-token | ssh spark1 'T=$(cat); HF_TOKEN=$T \
#     ~/services/colophon-worker/venv/bin/python -c "from huggingface_hub import hf_hub_download as d; \
#     [d(\"facebook/sam3.1\", f, local_dir=\"/home/colophon/models/sam3/sam3.1\") for f in (\"config.json\",\"sam3.1_multiplex.pt\")]"'
# then set COLOPHON_SAM_CKPT=~/models/sam3/sam3.1/sam3.1_multiplex.pt in the unit.

ls -l "$MODELS"

# The systemd --user unit (installed, not enabled).
if [ -f "$SVC/colophon-worker.service" ]; then
  mkdir -p "$HOME/.config/systemd/user"
  install -m 644 "$SVC/colophon-worker.service" "$HOME/.config/systemd/user/colophon-worker.service"
  systemctl --user daemon-reload
fi

"$VENV/bin/python" - <<'PY'
import torch, sam3, os
print("torch", torch.__version__, "cuda", torch.cuda.is_available(), torch.cuda.get_device_name(0))
print("sam3 from", os.path.dirname(sam3.__file__))
PY
[ -f "$SVC/worker_sam.py" ] && echo "worker: $SVC/worker_sam.py" || echo "worker_sam.py not copied yet"
echo "ok"
