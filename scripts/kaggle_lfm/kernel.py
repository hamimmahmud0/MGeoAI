"""Kaggle kernel: run LFM3-1.7B on every GPU of the session, with no tunnel and therefore no 100-second limit.

One llama.cpp server is started per GPU (a 1.7B model fits on one T4, so one copy per GPU keeps both GPUs fully busy),
and a small balancer sends each request to the less busy server. The project's own CLI then runs this shard's
share of the extraction and same-accident jobs against the balancer. This file is a template: push.sh fills in
SHARD, SHARDS and DATASET_SLUG.
"""

from __future__ import annotations

import glob
import http.client
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

SHARD, SHARDS, DATASET_SLUG = @@SHARD@@, @@SHARDS@@, "@@DATASET@@"
DEADLINE = time.time() + 8.5 * 3600  # Kaggle stops a session after 9 hours: skip what cannot finish
WORK = Path("/kaggle/working")
OUT = WORK / "out"
ROOT = WORK / "root"
LOG = WORK / "driver.log"
MODEL_REPO, MODEL_FILE = "LiquidAI/LFM3-1.7B-GGUF", "LFM3-1.7B-F16.gguf"  # full precision, not a compressed copy
PORT = 8080
BACKENDS = [8081, 8082]


def log(*parts: object) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] " + " ".join(str(p) for p in parts)
    print(line, flush=True)
    with LOG.open("a") as handle:
        handle.write(line + "\n")


def sh(command: str, check: bool = True, env: dict[str, str] | None = None, cwd: Path | None = None) -> int:
    log("$", command)
    result = subprocess.run(command, shell=True, env={**os.environ, **(env or {})}, cwd=cwd)
    if check and result.returncode:
        raise SystemExit(f"command failed ({result.returncode}): {command}")
    return result.returncode


def find_bundle() -> Path:
    hits = glob.glob(f"/kaggle/input/**/root/articles", recursive=True)
    if not hits:
        raise SystemExit("bundle dataset not found under /kaggle/input")
    return Path(hits[0]).parents[1]


def build_llama() -> Path:
    binary = WORK / "llama.cpp" / "build" / "bin" / "llama-server"
    if binary.exists():
        return binary
    sh("nvidia-smi -L")
    sh("nvcc --version | tail -2", check=False)
    sh("find / -name 'libcuda.so*' -not -path '*/proc/*' 2>/dev/null | head -20", check=False)
    sh("git clone --depth 1 https://github.com/ggml-org/llama.cpp", cwd=WORK)
    # CMake's CUDA::cuda_driver target needs a libcuda.so to link against; on a GPU image only the stub may exist
    dirs = sorted({str(Path(p).parent) for pat in ("/usr/local/cuda*/**/stubs/libcuda.so", "/usr/lib/x86_64-linux-gnu/libcuda.so*",
                                                  "/usr/local/nvidia/lib64/libcuda.so*") for p in glob.glob(pat, recursive=True)})
    log("libcuda dirs", dirs)
    base = "-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=75 -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF"
    attempts = [f"{base} -DCMAKE_LIBRARY_PATH={';'.join(dirs)} -DCUDAToolkit_ROOT=/usr/local/cuda",
                f"{base} -DCMAKE_LIBRARY_PATH={';'.join(dirs)} -DCUDAToolkit_ROOT=/usr/local/cuda -DGGML_CUDA_NO_VMM=ON"]
    for flags in attempts:
        shutil.rmtree(WORK / "llama.cpp" / "build", ignore_errors=True)
        if sh(f"cmake -B build {flags}", check=False, cwd=WORK / "llama.cpp") == 0:
            break
    else:
        raise SystemExit("cmake could not configure the CUDA build")
    sh("cmake --build build --target llama-server -j 4", cwd=WORK / "llama.cpp")
    return binary


def download_model() -> Path:
    from huggingface_hub import hf_hub_download

    return Path(hf_hub_download(MODEL_REPO, MODEL_FILE, local_dir=str(WORK / "model")))


class Balancer(http.server.BaseHTTPRequestHandler):
    load = [0] * len(BACKENDS)
    lock = threading.Lock()

    def _forward(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        with self.lock:
            i = min(range(len(BACKENDS)), key=lambda k: self.load[k])
            self.load[i] += 1
        try:
            conn = http.client.HTTPConnection("127.0.0.1", BACKENDS[i], timeout=3 * 3600)
            headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "connection")}
            conn.request(self.command, self.path, body, headers)
            response = conn.getresponse()
            data = response.read()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in ("transfer-encoding", "connection", "content-length"):
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:  # noqa: BLE001 - report to the client as a gateway error
            self.send_error(502, str(exc)[:200])
        finally:
            with self.lock:
                self.load[i] -= 1

    do_GET = do_POST = _forward

    def log_message(self, *args: object) -> None:  # silence
        pass


def start_balancer() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Balancer)
    threading.Thread(target=server.serve_forever, daemon=True).start()


class Servers:
    """One llama-server per GPU; restarted with another context/parallel setting for the long-prompt jobs."""

    def __init__(self, binary: Path, model: Path) -> None:
        self.binary, self.model = binary, model
        self.procs: list[subprocess.Popen] = []

    def start(self, gpus: list[int], ctx: int, parallel: int) -> None:
        self.stop()
        for n, gpu in enumerate(gpus):
            cmd = [str(self.binary), "-m", str(self.model), "--host", "127.0.0.1", "--port", str(BACKENDS[n]), "-ngl", "99",
                   "-c", str(ctx), "--parallel", str(parallel), "--jinja", "--top-k", "50", "--repeat-penalty", "1.1"]
            handle = (WORK / f"server{gpu}.log").open("a")
            self.procs.append(subprocess.Popen(cmd, stdout=handle, stderr=subprocess.STDOUT, env={**os.environ, "CUDA_VISIBLE_DEVICES": str(gpu)}))
            log("server", gpu, "ctx", ctx, "parallel", parallel)
        for n in range(len(gpus)):
            self.wait(BACKENDS[n])
        if len(gpus) == 1:  # the balancer must not send work to a stopped server
            BACKENDS[:] = [8081]
        else:
            BACKENDS[:] = [8081, 8082]
        Balancer.load = [0] * len(BACKENDS)

    @staticmethod
    def wait(port: int) -> None:
        for _ in range(600):
            try:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request("GET", "/health")
                if conn.getresponse().status == 200:
                    return
            except OSError:
                pass
            time.sleep(2)
        raise SystemExit(f"server on port {port} did not become ready")

    def stop(self) -> None:
        for proc in self.procs:
            proc.terminate()
        for proc in self.procs:
            try:
                proc.wait(30)
            except subprocess.TimeoutExpired:
                proc.kill()
        self.procs = []


def write_control() -> None:
    settings = {
        "labelling_open": True, "pricing": {}, "run_token_limit": 500_000_000, "max_images_per_article": 3,
        "run_cost_limit_usd": 5.0, "daily_cost_limit_usd": 20.0, "concurrency": 8,
        "providers": {"custom": {"model": "LFM3-1.7B", "base_url": f"http://127.0.0.1:{PORT}/v1", "timeout_seconds": 1800,
                                 "max_output_tokens": 2048, "supports_images": False, "thinking": "disabled",
                                 "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}},
    }
    (ROOT / "control.json").write_text(json.dumps(settings, indent=2), "utf-8")


def collect() -> None:
    OUT.mkdir(exist_ok=True)
    for path in glob.glob(str(ROOT / "runs" / "custom__lfm3*")) + glob.glob(str(ROOT / "matching" / "*@custom-*")):
        target = OUT / Path(path).relative_to(ROOT)
        shutil.copytree(path, target, dirs_exist_ok=True)
    shutil.copy(LOG, OUT / f"driver_shard{SHARD}.log")


def task(name: str, command: str) -> None:
    if time.time() > DEADLINE:
        log("skipped (out of time):", name)
        return
    log("TASK", name)
    start = time.time()
    code = sh(command, check=False, env={"CUSTOM_API_KEY": "none"})
    log("TASK done", name, "exit", code, f"{(time.time() - start) / 60:.1f} min")
    collect()


def main() -> None:
    bundle = find_bundle()
    log("bundle", bundle, "shard", SHARD, "of", SHARDS)
    binary = build_llama()
    model = download_model()
    shutil.rmtree(ROOT, ignore_errors=True)
    shutil.copytree(bundle / "root", ROOT)
    sh(f"pip install -q {bundle / 'code'}")
    write_control()
    start_balancer()
    servers = Servers(binary, model)
    try:
        servers.start([0, 1], ctx=262_144, parallel=4)
    except SystemExit:
        servers.start([0, 1], ctx=131_072, parallel=4)
    shard = f"--shard {SHARD}/{SHARDS}"
    run = f"mgeoai x run --provider custom --model LFM3-1.7B --input-set markdown --with-meta --concurrency 8 {shard} --root {ROOT}"
    group = f"mgeoai x group-run --provider custom --model LFM3-1.7B --root {ROOT} --token-limit 500000000 --concurrency 8 {shard}"
    task("extraction, reasoning off", run)
    task("extraction, reasoning on", run + " --reasoning")
    task("pair-fields both, reasoning off", group + " --method pair-fields --variant both")
    task("pair-fields both, reasoning on", group + " --method pair-fields --variant both --reasoning")
    task("pair-full, reasoning off", group + " --method pair-full")
    task("pair-full, reasoning on", group + " --method pair-full --reasoning")
    if SHARD == 0:  # one clustering request covers all 244 articles (about 118,000 tokens): one server, one slot
        servers.start([0], ctx=262_144, parallel=1)
        task("cluster-cards, reasoning off", group + " --method cluster-cards --repeats 3")
        task("cluster-cards, reasoning on", group + " --method cluster-cards --repeats 3 --reasoning")
    servers.stop()
    collect()
    log("ALL DONE")


if __name__ == "__main__":
    try:
        main()
    finally:
        collect()
