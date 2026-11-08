# Deployment (VPS 165.99.219.95, user `mgeoai`)

### 2026-10-20
- Code: `~/MGeoAI` cloned from GitHub `main` (32502f27), venv at `~/MGeoAI/.venv`. `web/dist` and `extraction/articles` (244 articles + images, 220 MB) copied with rsync from the laptop; `web/dist/assets` is not tracked in git, so a plain clone serves a blank page.
- Service: `~/.config/systemd/user/mgeoai.service` (enabled, linger on, MemoryMax 900M), listens on 127.0.0.1:8791. Env (session secret, extraction dir, secure cookies) in `~/.config/mgeoai/env` (mode 600). Accounts generated on the server; passwords in `~/MGeoAI/extraction/initial_passwords.txt` (mode 600).
- Update procedure (rsync is the deploy method; the VPS clone has locally synced files, so do not `git pull` there): rsync `src/`, `pyproject.toml`, `assets/mllm_prompts/`, `web/dist/` (with --delete) from the laptop, `pip install -e .` if dependencies changed, then `systemctl --user restart mgeoai`.
- Cloudflare: the two existing tunnels are token-managed (ingress lives in the dashboard) and belong to other users; not touched. The app needs a public hostname rule pointing at `http://127.0.0.1:8791`. The API token in `.creds` is IP-restricted and lacks tunnel permission, so this step is manual.
- Not deployed: API keys (enter them in the control panel; they live in server memory only).

### 2026-10-20 (later)
- Deployed the open dashboard build (public Map/score/model tabs, retry failed, scoring). Public routes are locked while `labelling_open` is true (default).

### 2026-11-08 — backup worker
- Private Hugging Face bucket `hamimmahmud0/mgeoai-backup` (README.md inside is `docs/BUCKET_README.md`). Independent systemd user timer `mgeoai-backup.timer` (00/06/12/18:00 UTC, persistent) runs `mgeoai x backup` on the VPS; token in `~/.config/mgeoai/hf.env` (mode 600), state in `~/MGeoAI/backup_state/`. `latest/` is a non-deleting mirror; a `history/<UTC>/` entry is written only when labels, runs or settings changed; `manifest/status.json` shows `last_backup_utc` (stale > 7 h = worker down). Accounts, password files and API keys are never backed up.
- Manual run: `systemctl --user start mgeoai-backup.service`; logs: `journalctl --user -u mgeoai-backup`.
- Restore: `hf buckets sync hf://buckets/hamimmahmud0/mgeoai-backup/latest ./extraction` (see the bucket README).
- Laptop copies: `~/mgeoai-backups/` (snapshots, state, report). The HF token on the VPS can write to every repo of the account; replace it with a fine-grained token limited to this bucket.
