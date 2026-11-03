# Colophon SAM 3.1 worker on spark2

The second worker. It runs the same code as spark1 with the same recipe. **`deploy/spark1/README.md` is the reference**:
it covers the weights, how the worker runs SAM, and the traps. This file records only what was done on spark2 and
what was different there.

**State on 2026-11-02 22:51 EST: the unit is enabled and running** (`systemctl --user`, `--name spark2`; colophon
already had `Linger=yes` on spark2, so linger was not changed). It leases pages from the coordinator on hub
(`http://hub:8101`) next to spark1.

## What is where (spark2)

| What | Where |
|---|---|
| uv | `~/tools/uv/uv` (**new**: spark2 had no uv, see below) |
| venv (Python 3.12) | `~/services/colophon-worker/venv` |
| worker | `~/services/colophon-worker/worker_sam.py` (copy of `colophon/worker_sam.py`) |
| SAM 3 code | `~/services/colophon-worker/sam3-src` (facebookresearch/sam3 @ `f1647e8`, editable) |
| weights | `~/models/sam3/sam3.1_multiplex_fp16.safetensors`, a hard link to spark2's own ComfyUI copy |
| unit | `~/.config/systemd/user/colophon-worker.service` (spark1's unit with `--name spark2`) |
| logs | `~/scratch/2026-11-02-colophon/worker.log` (also `journalctl --user -u colophon-worker`) |
| test pages + result | `~/scratch/2026-11-02-colophon/pages/13187/{0017,0020,0022}.jpg`, `local-13187.json` |

Nothing at the top of `~`, no sudo. No container or service was stopped, restarted or reconfigured. ComfyUI kept its
~15 GB on the GPU throughout.

## Install / update

```bash
# from the repo on the Mac; the unit is spark1's with --name spark2
sed 's/--name spark1/--name spark2/' deploy/spark1/colophon-worker.service > /tmp/colophon-worker.service
scp colophon/worker_sam.py /tmp/colophon-worker.service spark2:services/colophon-worker/
ssh spark2 'UV=$HOME/tools/uv/uv bash -s' < deploy/spark1/install.sh   # idempotent; same script as spark1
ssh spark2 systemctl --user restart colophon-worker                      # after a worker update
```

Operate it the same way as spark1 (`ssh spark2 systemctl --user status|stop|start colophon-worker`).
`curl -s http://hub:8101/status` shows both workers under `workers`.

## What differed from spark1

- **No uv on spark2.** `~/.local/bin/uv` does not exist there, and neither does any other uv. spark1's own binary
  (uv 0.11.29, aarch64) was copied to `~/tools/uv/uv`, and `install.sh` ran with `UV=$HOME/tools/uv/uv`. The
  script already reads `UV` from the environment, so it needed no change.
- **The weights were already there.** spark2's ComfyUI has the same repack,
  `~/models/comfyui/checkpoints/sam3.1_multiplex_fp16.safetensors`, with the **same sha256 as spark1's**
  (`9ba99c92…6368eb03`). `install.sh` hard-linked it into `~/models/sam3/` (link count 2). Nothing was copied from
  spark1.
- The install took **6 min**: torch's wheels downloaded from scratch, and the 2 min 59 s download was the slow part.
  The resolved packages match spark1, including sam3's `numpy<2` pin pulling numpy back to 1.26.4 and opencv to
  4.11.

## Measured (2026-11-02)

Local test (`--local`, 3 pages of book 13187). The detection counts are **identical to spark1's** where spark1 recorded
them:

| page | spark2 | spark1 |
|---|---|---|
| 17 | 9 `photograph` (1.56 s, first page) | 9 |
| 20 | 2 `photograph` (0.64 s) | (not recorded) |
| 22 | 31 `photograph` (1.21 s) | 31 |

Model load 5.3 s, peak GPU memory 4.26 GB (nvidia-smi 4.5 GB for the process).

Against the coordinator, both workers at once, sampled every 30 s from 03:51:27 to 03:54:59 UTC (212 s):

| | pages | pages/min | mean s/page | failed |
|---|---|---|---|---|
| spark2 | 334 | **94.5** | 0.62 | 0 |
| spark1 | 337 | 95.4 | 0.60 | 0 |
| **combined** | 671 | **~190** | | 0 |

spark1's rate did not drop when spark2 joined (it was 96–97 pages/min alone). Adding the second Spark roughly doubles
throughput. At ~190 pages/min the ~74,900 queued pages take about **6.5 h**. The coordinator's own `eta_minutes`
(699 at 03:55) is computed from the last hour's rate, which was mostly spark1 alone, so it is too high until an hour
has passed.

spark2 under the service: GPU 74–86 % utilisation, 76 °C, ~53–64 W, 2.47–2.52 GHz SM clock. ComfyUI was idle.

## Not verified

- Behaviour while ComfyUI or a front end renders on spark2's GPU. Both were idle during the run, and `the GPU gate` does
  not know about this worker. A render will share the GPU with it, and both will slow down.
- The rate over a long run. Only 3.5 minutes were measured.
