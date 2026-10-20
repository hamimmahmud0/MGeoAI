# Deployment (VPS 165.99.219.95, user `mgeoai`)

### 2026-10-20
- Code: `~/MGeoAI` cloned from GitHub `main` (32502f27), venv at `~/MGeoAI/.venv`. `web/dist` and `extraction/articles` (244 articles + images, 220 MB) copied with rsync from the laptop; `web/dist/assets` is not tracked in git, so a plain clone serves a blank page.
- Service: `~/.config/systemd/user/mgeoai.service` (enabled, linger on, MemoryMax 900M), listens on 127.0.0.1:8791. Env (session secret, extraction dir, secure cookies) in `~/.config/mgeoai/env` (mode 600). Accounts generated on the server; passwords in `~/MGeoAI/extraction/initial_passwords.txt` (mode 600).
- Update procedure (rsync is the deploy method; the VPS clone has locally synced files, so do not `git pull` there): rsync `src/`, `pyproject.toml`, `assets/mllm_prompts/`, `web/dist/` (with --delete) from the laptop, `pip install -e .` if dependencies changed, then `systemctl --user restart mgeoai`.
- Cloudflare: the two existing tunnels are token-managed (ingress lives in the dashboard) and belong to other users; not touched. The app needs a public hostname rule pointing at `http://127.0.0.1:8791`. The API token in `.creds` is IP-restricted and lacks tunnel permission, so this step is manual.
- Not deployed: API keys (enter them in the control panel; they live in server memory only).

### 2026-10-20 (later)
- Deployed the open dashboard build (public Map/score/model tabs, retry failed, scoring). Public routes are locked while `labelling_open` is true (default).
