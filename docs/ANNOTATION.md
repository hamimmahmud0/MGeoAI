# Benchmark annotation (T01)

Blind pair labelling for the matching benchmark. Annotators are reviewer accounts.

```bash
mgeoai annotate init-users hamim oishik mubasshir rubayet   # writes annotation/reviewers.json + initial_passwords.txt (0600)
export MGEOAI_REVIEWERS_JSON="$(cat annotation/reviewers.json)"
export MGEOAI_SESSION_SECRET="$(python -c 'import secrets;print(secrets.token_urlsafe(40))')"
mgeoai serve --host 127.0.0.1 --port 8000     # open /, sidebar: Benchmark annotation
```

- Items: `annotation/items.json` (served) and `annotation/admin_meta.json` (never served).
  `mgeoai annotate import-items FILE` refuses once labels exist unless `--force`.
- Labels: `annotation/labels/<name>.jsonl`, append-only, latest wins. Names must match
  `^[a-z][a-z0-9_]{1,31}$`.
- Progress and results: `mgeoai annotate status | agreement | export`.
- Everything under `annotation/` and `benchmark/pages/` is git-ignored (third-party text, secrets).
- There is no password change page or login lockout: passwords are fixed at issue time
  (`mgeoai hash-reviewer-password` to set your own), as for the reviewer workspace.
- `benchmark/scraps/` holds the browser agent's grouping (match vs decoy) and is git-ignored
  until annotation closes, so annotators who can read the repo cannot see it. Commit it afterwards.
- Do not serve a pipeline run over these pages from the annotators' server before labelling ends:
  Overview and Sources would reveal which articles the pipeline clustered.
- Generate `MGEOAI_SESSION_SECRET` once and keep it in a 0600 file; a new value at each start
  signs everyone out. `MGEOAI_REVIEWERS_JSON` replaces any other configured reviewers: merge if needed.
- `init-users` keeps existing accounts unless `--reset`, and merges new names.
