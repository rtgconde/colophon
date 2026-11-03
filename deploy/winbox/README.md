# winbox: SAM 3.1 worker host for Colophon

winbox is the owner's Windows 11 gaming PC (RTX 4090, 24 GB). It runs the Colophon SAM worker **only when it is started by
hand over SSH**. There is no scheduled task, no service, and nothing that starts at boot or logon (checked: 0 tasks and
0 services mention `colophon`). A reboot ends the worker, and that is intended.

Set up 2026-11-02. Everything below was measured on the machine that day unless marked *unverified*.

## What is where

| Path on winbox | What |
|---|---|
| `C:\ProgramData\colophon\venv\` | Python 3.12.10 venv (from the system `python` on PATH) |
| `C:\ProgramData\colophon\models\sam3.1_multiplex_fp16.safetensors` | SAM 3.1 Object Multiplex, fp16, 1,745,546,848 bytes, sha256 `9ba99c92703c2e8b4f47de2d34a539bb8e18923049e238b780d70dbe6368eb03` (the same file as spark1's `~/models/sam3/`) |
| `C:\ProgramData\colophon\run-worker.cmd` | activates the venv and runs the worker, appending to `worker.log` |
| `C:\ProgramData\colophon\start-worker.ps1` / `stop-worker.ps1` / `status-worker.ps1` | control over SSH (copies of the files in this folder) |
| `C:\ProgramData\colophon\worker_sam.py` | **not there yet**: you copy it in (`colophon/worker_sam.py`) |
| `C:\ProgramData\colophon\worker.log`, `worker.pid`, `worker.stop` | runtime: the log, the PID of the `cmd.exe` running `run-worker.cmd`, and the stop flag |
| `C:\ProgramData\colophon\smoke.py`, `test\` | smoke test (`smoke.py` here) + 5 test pages, boxed previews and `smoke-result.json` |

That is about 6.3 GB in total.

## Installed packages (pip, inside the venv)

```powershell
$py = 'C:\ProgramData\colophon\venv\Scripts\python.exe'
python -m venv C:\ProgramData\colophon\venv
& $py -m pip install --upgrade pip                                   # -> 26.3
& $py -m pip install torch==2.10.0 torchvision --index-url https://download.pytorch.org/whl/cu128
& $py -m pip install "setuptools<81" wheel                           # sam3 imports pkg_resources; 3.12 venvs ship no setuptools
& $py -m pip install C:\ProgramData\colophon\sam3-f1647e8.zip        # see "sam3 source" below
& $py -m pip install "triton-windows<3.7" pycocotools einops psutil
```

Result: `torch 2.10.0+cu128` (CUDA 12.8, `cuda.is_available() True`, "NVIDIA GeForce RTX 4090"), `torchvision 0.25.0+cu128`,
`sam3 0.1.0` @ facebookresearch/sam3 commit `f1647e8d0c1d` (2026-10-23), `triton-windows 3.6.0.post26`, `numpy 1.26.4`
(pinned `<2` by sam3; it downgraded the 2.5.4 that torch pulled in), `timm 1.0.30`, `huggingface_hub 2.4.0`,
`safetensors 0.8.0`, `pillow 13.0.0`, `pycocotools 2.0.11` (Windows wheel, no compiler needed), `psutil 7.2.2`,
`setuptools 78.1.0`. The driver is 617.14 (CUDA 13.4), so cu128 wheels run as-is.

**No C++/CUDA build is needed.** sam3 is pure Python (setuptools, no `ext_modules`). The native pieces are all optional:
FlashAttention 3 (`use_fa3`, off by default), `cc_torch` (video tracker only) and the triton EDT kernel (video tracker
only). Windows has no Visual Studio Build Tools here, and none were needed.

**sam3 source.** `pip install git+https://github.com/facebookresearch/sam3.git@<sha>` stalled for 12+ min on winbox
inside `git clone --filter=blob:none`. A `git archive` zip of the same commit, made on the Mac and copied over, installed
in seconds. The zip has been deleted from winbox, so to reinstall, make it again:
`git clone --depth 1 https://github.com/facebookresearch/sam3.git && git -C sam3 archive --format=zip --prefix=sam3-src/ -o sam3-f1647e8.zip HEAD`.

## Weights: why the ComfyUI fp16 file, not Hugging Face

`facebook/sam3.1` (`sam3.1_multiplex.pt`) and `facebook/sam3` are **gated**. The sealed HF token authenticates, but this
account is **not on either access list** (`GatedRepoError: ... you are not in the authorized list`). Fixing that needs the
owner: log in at <https://huggingface.co/facebook/sam3.1>, request access and accept Meta's terms.

What we use instead is `sam3.1_multiplex_fp16.safetensors`, the fp16 SAM 3.1 checkpoint that already sits in all three
ComfyUI libraries (spark1, spark2, mlbox; on the estate since 2026-10-06). It was copied from spark1 and the sha256 was
verified. Its `detector.*` half is loaded into the official image model, which is exactly what the official sam3 loader
does with a 3.1 checkpoint (and what `worker_sam.py` on spark1 does):

```python
model = build_sam3_image_model(device="cpu", load_from_HF=False, checkpoint_path=None, eval_mode=True)
sd = safetensors.torch.load_file(CKPT)
det = {k[len("detector."):]: v for k, v in sd.items() if k.startswith("detector.")}
missing, unexpected = model.load_state_dict(det, strict=False)   # 1133 keys; 37 missing, 36 unexpected
```

The 37 "missing" keys are the RoPE `freqs_cis` buffers, which are recomputed at init. The 36 "unexpected" keys are
`interactive_convs.*`, the SAM-1-style interactive neck that the image model builds only with `enable_inst_interactivity`.
Neither one matters for text-prompted detection, and the results below confirm that.

## Smoke test (2026-11-02, `smoke.py`)

The test used five pages of book 13187 (*Thomas Demand*, MoMA 2005): 0010, 0020, 0045, 0060 and 0090. Each page is about
2000×1520, landscape spreads. Settings: 8 prompts (painting, photograph, drawing, print, sculpture, map, diagram,
illustration), score ≥ 0.30, bf16 autocast, image embedded once with `set_image`, then one `set_text_prompt` per prompt.
`Sam3Processor` returns **every** query above the threshold (not just the best one), and 0020 returned two `photograph`
boxes from one prompt.

| | |
|---|---|
| model load (CPU build + safetensors + `.cuda()`) | 7.1 s |
| first page (CUDA warm-up) | 1.46 s |
| **steady state, all 8 prompts** | **0.727 s/page** (min 0.716, max 0.740); image embed ≈ 0.043 s, about 0.085 s per prompt |
| GPU memory | weights 3.33 GiB; peak allocated 5.00 GiB, peak reserved 5.22 GiB (of 24 GB; the desktop uses about 2.4 GB) |

| page | detections (score ≥ 0.30) | what is there |
|---|---|---|
| 0010 | 0 | the contents page, text only. Correct |
| 0020 | 2 × photograph (0.785, 0.762) | text spread with two figures: the Riefenstahl stadium photograph (box tight on the image), and fig. 9, the catalogue frontispiece with Hitler and Speer. That box is tight on the photo inside the reproduced catalogue page and leaves out the page's German text and signature. Both are real figures; no text block was boxed |
| 0045 | 0 | a blank page with a small plate caption. Correct |
| 0060 | 1 × photograph (0.43) | a full-bleed plate (an office interior) across the spread. The box is the whole image, ≈ 97 % of the page |
| 0090 | photograph 0.707 + photograph 0.346 | a plate on the right page (a yellow raincoat in a dim room). The 0.71 box is tight on the plate. The 0.35 box is the whole spread |

Only `photograph` fired. That fits this book (Demand's work is photographs), but the other seven prompts have **not**
been seen to fire on a book that has them (paintings, maps, drawings). That is unverified.

**Two findings for post-processing (PROTOCOL.md step 2):** the "drop boxes over 95 % of the page" rule removes 0060's
real full-bleed plate (≈ 97 %) along with 0090's whole-spread false box (≈ 96 %). Full-bleed plates are common in these
catalogues. Consider keeping a > 95 % box when it is the only detection on the page, or when its score is ≥ 0.4.

## Running the worker over SSH

Copy the worker in first (from the Mac):

```bash
scp colophon/worker_sam.py winbox:C:/ProgramData/colophon/worker_sam.py
scp deploy/winbox/{run-worker.cmd,start-worker.ps1,stop-worker.ps1,status-worker.ps1} winbox:C:/ProgramData/colophon/
```

Then:

```bash
ssh winbox 'powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\colophon\start-worker.ps1'
ssh winbox 'powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\colophon\status-worker.ps1'
ssh winbox 'powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\colophon\stop-worker.ps1'          # flag, 30 s grace, then kill
ssh winbox 'powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\colophon\stop-worker.ps1 -Force'   # kill now
```

- `start-worker.ps1` refuses to start a second copy, clears a stale `worker.stop`, launches
  `cmd.exe /c run-worker.cmd` through **`Win32_Process.Create`**, writes the PID to `worker.pid`, and shows the
  children and the log tail. `-ExtraArgs '--batch 8'` passes extra flags to the worker.
- `run-worker.cmd` runs
  `worker_sam.py --coordinator http://hub:8101 --name winbox --ckpt C:\ProgramData\colophon\models\sam3.1_multiplex_fp16.safetensors`
  with `HF_HUB_OFFLINE=1` and `PYTHONUNBUFFERED=1`, appending stdout and stderr to `worker.log`. It also sets
  `COLOPHON_SAM_CKPT` to the same path.
- `stop-worker.ps1` writes `C:\ProgramData\colophon\worker.stop`, waits up to `-GraceSeconds` (30) for the worker to exit,
  then runs `taskkill /PID <pid> /T /F`. A page killed mid-run is re-queued when its 20-minute lease expires.
- Tested with a stand-in script: start, survival across SSH sessions, refusal of a second start, graceful stop through
  the flag, and forced kill (0 leftover processes). **Not yet tested with the real `worker_sam.py`.**

## For the author of `worker_sam.py` (Windows issues in the spark1 draft, read 2026-11-02)

1. **`os.uname()` does not exist on Windows.** `ap.add_argument("--name", default=os.uname().nodename...)` is evaluated
   while the parser is built, so the worker crashes with `AttributeError` even though `--name winbox` is passed. Use
   `platform.node()` or `socket.gethostname()`.
2. **No SIGTERM on Windows.** A detached session-0 process cannot be sent SIGINT/SIGTERM, and `taskkill /F` is an
   immediate TerminateProcess. For a clean stop, check `os.path.exists(r"C:\ProgramData\colophon\worker.stop")`
   between pages (any path works if it is passed in; `stop-worker.ps1` creates exactly this file), and exit 0.
3. `DEFAULT_CKPT` uses `~`. Under SSH/WMI that resolves to the wrong profile, which is why `run-worker.cmd` passes
   `--ckpt` explicitly.
4. **Desk-wins on this host:** the worker runs in session 0 as a background process, so `GetLastInputInfo` sees no user
   input. To detect someone at the PC, read the console session's idle time from `query user`
   (`quser`, the IDLE TIME column; a "." means active now), or check for a running game / GPU load. *Unverified idea, not
   built.*

## Traps hit while setting this up

- **A `Start-Process` child dies when the SSH session ends.** Win32-OpenSSH puts the session's processes in a job
  object. Tested: a `Start-Process -WindowStyle Hidden` child was gone a few seconds after `ssh` returned, while a
  `Win32_Process.Create` (`Invoke-CimMethod`) child was still running. The start script therefore uses CIM.
- **Never pipe a secret into `powershell -Command -`.** PowerShell reads stdin *as the script*, so
  `[Console]::In.ReadLine()` gets nothing, the secret line is **executed as a command**, and it comes back verbatim in
  the "is not recognized as a cmdlet" error. This happened once with the HF token (see Open items). What works:
  `get-secret hf-token | ssh winbox "C:\...\python.exe C:\...\script.py"`, with the script reading
  `sys.stdin.readline()` and passing `token=` to `hf_hub_download`. PowerShell never parses the line, and nothing is
  written to disk or put on a command line.
- **zsh `echo` mangles Windows paths:** `\c` in `C:\ProgramData\colophon` means "stop output" to zsh's echo, so the
  remote script was cut off silently. Feed scripts with a quoted heredoc (`<<'EOF'`), never `echo`.
- **Python warnings on stderr make PowerShell report `NativeCommandError`**, which looks like a failure. `timm`'s
  deprecation warning did this while the import actually worked. Read the stdout, or redirect stderr.
- `pip install git+https://...` hung in a partial clone on winbox. Ship a `git archive` zip instead.
- A Python 3.12 venv has no `setuptools`, and sam3 imports `pkg_resources`. Install `setuptools<81`.
- sam3 imports `triton` (from `sam3/model/edt.py`, through `model_builder`) and `psutil` at import time, even for the
  image model. On Windows that means `triton-windows` (only the import is needed; the kernel runs only in video
  tracking) and `psutil`.
- The GPU's ~2.4 GB / ~12 % "use" at idle is the desktop (dwm, launchers, a launcher, utilities…), not a compute
  job. Nothing was stopped.

## Open items

- **Rotate the Hugging Face token** (`hf-token` in `the secret store`). It was echoed once into this setup session's
  transcript on the Mac by the stdin trap above. It did not reach disk on winbox: the PowerShell event log (4104/4100)
  and PSReadLine history were checked and contain no `hf_…` string.
- Owner: request access to `facebook/sam3.1` on Hugging Face if the official `.pt` checkpoint is wanted. It is not
  needed for this worker.
- Run the worker against a book with paintings, maps or drawings, to see the other prompts fire.
- Speed headroom (not tried): each prompt re-runs the fusion encoder and decoder (≈ 85 ms). Batching all 8 prompts into
  one grounding pass, or `compile=True`, could cut the 0.73 s/page.
