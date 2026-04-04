# MLOps & Production Engineering Training Guide

A hands-on course using the NYC Weather Nowcaster as the training ground.
Each module introduces a concept, explains why it matters in production ML,
and gives you a concrete problem set that builds real functionality into the repo.
Modules are ordered by dependency — complete them in sequence.

Earlier concepts are deliberately revisited in later modules. By the end,
branching, testing, Docker, and cron will feel like second nature.

---

## Module 1 — Git Workflow & Branching Strategy

### Why it matters
On a team (or even solo with multiple machines), working directly on `main` is dangerous.
A bad commit can break production. Branches give you an isolated workspace.

### Concepts
- `main` — always deployable. Nothing broken lives here.
- Feature branches — one branch per feature or fix. Short-lived. Merged via pull request.
- Merge conflicts — when two branches change the same lines. Git can't decide which wins, so you do.
- `git log --oneline --graph` — visualize branch history

### The branching workflow
```bash
git checkout -b feature/my-feature   # create and switch to new branch
# ... make changes ...
git add src/weather/pipelines/...
git commit -m "Add my feature"
git push origin feature/my-feature
# Open a pull request on GitHub
```

### Resolving merge conflicts
Conflicts look like this in a file:
```
<<<<<<< HEAD
    crashes_lag: 5
=======
    crashes_lag: 4
>>>>>>> feature/new-lags
```
- Everything between `<<<<<<< HEAD` and `=======` is your current branch
- Everything between `=======` and `>>>>>>>` is the incoming branch
- Delete all three marker lines and keep whichever version is correct (or combine them)

After resolving:
```bash
git add conf/base/parameters.yml
git commit -m "Resolve merge conflict in parameters.yml"
```

### Protecting main
On GitHub: Settings → Branches → Add rule → require PR reviews + require CI to pass.
This prevents anyone (including yourself) from pushing directly to `main`.

### Problem set
1. Initialize this repo with git if not already done: `git init && git add . && git commit -m "Initial commit"`
2. Create a branch `feature/add-gitignore-data` and confirm `data/` is properly ignored
3. Create a second branch `feature/test-conflict` from an older commit, change `crashes_lag` to `4`, commit it. Then on `main` change `crashes_lag` to `6`. Merge `feature/test-conflict` into `main`. Resolve the conflict in favor of `6`. Use `git log --oneline --graph` to see what happened.
4. Set up `.github/PULL_REQUEST_TEMPLATE.md` that prompts for: what changed, how to test it, whether `parameters.yml` was updated, and whether the Docker image needs a rebuild.

---

## Module 2 — Environment & Dependency Management

### Why it matters
"Works on my machine" is a production disaster. Pinned dependencies ensure every environment — your laptop, Docker, CI — runs identical code.

### Concepts
- `pyproject.toml` / `requirements.txt` — what your code needs
- Pinned vs. unpinned dependencies — `xgboost==2.1.0` vs. `xgboost>=2.0`
- Virtual environments — isolate project dependencies from system Python
- Lock files — snapshot of every transitive dependency at a point in time

### In this repo
```bash
# See what's installed and at what version
pip freeze > requirements-lock.txt

# The venv lives at .venv/ — never commit it (.gitignore already excludes it)
# pyproject.toml defines the declared dependencies
```

### Git practice for this module
All changes in this module go on a branch. This is now the rule for every module.

```bash
git checkout -b feature/dependency-management
# ... make changes ...
git commit -m "Add pip-tools and lock file"
git push origin feature/dependency-management
# Open a PR — even if you're the only reviewer, practice the workflow
```

**Common conflict zone:** `pyproject.toml` and `requirements.txt` are frequently
edited by multiple branches. If you hit a conflict here, the resolution is usually
to include both sets of dependencies, then re-run `pip-compile` to regenerate the lock file.

### Docker connection
The `Dockerfile` runs `pip install -e .` using whatever is in `pyproject.toml`.
Pinned dependencies mean the Docker image is reproducible — build it today or
in six months and you get the same environment.

After completing this module, rebuild the Docker image to verify your lock file
produces a working container:
```bash
docker compose build
docker compose run pipeline kedro run --pipeline inference
```

### Problem set
1. Run `pip freeze` and inspect the output. How many packages are installed that you didn't explicitly request?
2. Add `pip-tools` to the project and generate a `requirements.txt` from `pyproject.toml` using `pip-compile`. Compare to `pip freeze`.
3. Intentionally break the environment: uninstall `shap`, run `kedro run --pipeline inference`, observe the error. Re-install it. What does this tell you about implicit dependencies?
4. Add a `Makefile` with targets: `make install` (create venv + install), `make run-pipeline` (run data_engineering), `make run-inference`. This becomes the standard entrypoint for anyone new to the repo.
5. Add `make docker-build` and `make docker-up` to the Makefile. Merge your branch to `main` via PR.

---

## Module 3 — Configuration Management

### Why it matters
Hardcoded values in code are a production liability. When a lag changes, a threshold changes, or you want to run an experiment, you don't want to touch source code — you change config.

### Concepts
- Separation of code and config — logic in Python, tunables in YAML
- Environment-specific config — dev vs. prod may have different `end_date`, `train_subsample_frac`
- Secrets management — API keys, credentials never go in config files or git

### In this repo
Kedro's `conf/base/parameters.yml` already does this well. The next step is environment layering:
```
conf/
  base/         ← shared defaults (committed)
  local/        ← machine-specific overrides (gitignored)
  prod/         ← production overrides (committed, no secrets)
```

### Git practice for this module
Config changes are some of the most conflict-prone changes in any repo.
Practice the following discipline:

- **Never** mix config changes with code changes in the same commit
- When `parameters.yml` changes, always note it in the PR description
- If two branches both change `parameters.yml`, resolve by reading both sets of changes carefully — don't just pick one side blindly

```bash
git checkout -b feature/config-layering
```

**Simulated conflict exercise:** On your branch, change `train_subsample_frac` to `0.15`.
On `main`, change it to `0.3`. Merge. Resolve by keeping `0.3` (the main branch value
represents what's tested in production). Document your reasoning in the commit message.

### Docker and cron connection
The `docker-compose.yml` passes config into containers via environment variables or
bind-mounted `conf/` directories. Production config (`conf/prod/`) is baked into the
image at build time — which means a config change requires a Docker rebuild.

Update `docker-compose.yml` to mount `conf/` as a bind mount rather than copying it
into the image. This means config changes take effect without rebuilding:
```yaml
volumes:
  - ./conf:/app/conf
  - ./data:/app/data
```

After this change, your cron job no longer requires a Docker rebuild when parameters change.
This is a real production improvement.

### Problem set
1. Create `conf/local/parameters.yml` with `end_date` set to yesterday and `train_subsample_frac: 0.05` for fast local iteration. Verify `kedro run` picks it up without touching `conf/base/`.
2. Add `conf/local/` to `.gitignore`. Add inline comments in `conf/base/parameters.yml` explaining each parameter and its valid range.
3. Refactor the Dockerfile to copy `conf/base/` and `conf/prod/` but not `conf/local/`. Verify `docker compose build && docker compose run pipeline kedro run` still works.
4. Create `conf/base/credentials.yml.example` (committed) and `conf/base/credentials.yml` (gitignored). Document the pattern in README.
5. Open a PR. In the PR description, explain which parameters a new team member would most likely need to change and why.

---

## Module 4 — Logging & Observability

### Why it matters
In production, you can't `print()` and watch. When something breaks at 3am, logs are
your only window into what happened. Structured logs are searchable and parseable by
monitoring systems.

### Concepts
- Python `logging` module vs. `print()` — levels (DEBUG, INFO, WARNING, ERROR)
- Structured logging — JSON format so logs can be queried (e.g. `jq '.lag_hours'`)
- What to log in a pipeline: data shape, null rates, model scores, timing, API calls

### Git practice for this module
Logging changes touch almost every file in the codebase. This is a good moment
to practice **atomic commits** — one logical change per commit, not one giant commit
at the end.

```bash
git checkout -b feature/structured-logging
git add src/weather/pipelines/data_engineering/nodes.py
git commit -m "Replace print() with logging in data_engineering nodes"
git add conf/base/logging.yml
git commit -m "Configure JSON structured logging output"
git add src/weather/pipelines/data_science/nodes.py
git commit -m "Replace print() with logging in data_science nodes"
```

When reviewing this PR, each commit tells a clear story. Compare this to a single
"Add logging everywhere" commit — which is harder to review and harder to revert
if one part has a bug.

### Docker and cron connection
Logs written inside the container need to reach you. The `./logs/` bind mount in
`docker-compose.yml` already handles this. But the cron job runs `docker exec`, which
means its stdout goes to the cron log, not the container log.

Add a log rotation policy to prevent `logs/cron.log` from growing unbounded.
Update your crontab entry:
```bash
# Rotate cron log weekly, keep 4 weeks
0 0 * * 0 mv ~/code/project-weather-dumb/logs/cron.log ~/code/project-weather-dumb/logs/cron.log.$(date +\%Y\%W) && find ~/code/project-weather-dumb/logs/ -name "cron.log.*" -mtime +28 -delete
```

This is a cron job managing another cron job's artifacts — a common production pattern.

### Problem set
1. Replace all `print()` statements in `src/weather/pipelines/data_engineering/nodes.py` with `logging.getLogger(__name__)` calls at appropriate levels (INFO for progress, WARNING for empty responses).
2. Configure Kedro's logging in `conf/base/logging.yml` to write structured JSON logs to `logs/pipeline.json`. Install `python-json-logger`.
3. Add a node called `validate_features` to the data_engineering pipeline after `merge_features`. It should log: total rows, null rate per feature column, and date range. Log WARNING if any feature has >50% nulls.
4. Add timing instrumentation: log how long each fetch function takes. Which source is slowest?
5. Add the log rotation cron entry above. Verify `crontab -l` shows it. Open a PR with all logging changes — use atomic commits as described above.

---

## Module 5 — Data Validation & Pipeline Contracts

### Why it matters
Silent data corruption is worse than a crash. If the MTA API changes its schema,
you want to know immediately — not six hours later when the model produces garbage.

### Concepts
- Schema validation — expected columns, types, value ranges
- Data contracts — explicit agreement between pipeline stages about what data looks like
- Pandera — DataFrame validation library
- Fail fast — better to crash loudly at ingestion than silently at training

### Git practice for this module
Schema definitions are contracts between pipeline stages. Treat them like public APIs —
**don't break them without a PR that explains why**.

Practice reviewing your own PR before merging:
1. Push your branch
2. Open the PR on GitHub
3. Read every line of the diff as if you were a reviewer who didn't write it
4. Leave at least one comment on your own PR noting a tradeoff you made
5. Merge

This builds the habit of PR self-review, which catches bugs before teammates do.

**Conflict scenario:** You add a `pandera` schema requiring `ft_mta_lirr` to be non-null.
A teammate's branch removes LIRR from the feature set. Merging these two branches
creates a schema conflict — the validation will fail at runtime even though git reports
no conflict. This is a **semantic conflict** (git can't detect it). Only good PR review
and communication catches these. Add a note about this in the PR template you built in Module 1.

### Docker connection
Validation failures should stop the pipeline before writing any parquet files.
Verify this works inside the container:
```bash
docker compose run pipeline kedro run --pipeline data_engineering
# Observe where it fails when you inject a bad schema
```

### Problem set
1. Install `pandera` and write a schema for `hourly_features`: `ft_nyiso_load_mw` (float, >0, <100000), `tgt_precip` (categorical, one of clear/cloudy/rainy/snowy), DatetimeIndex with no duplicates.
2. Add the schema validation as a Kedro node between `merge_features` and downstream consumers.
3. Write schemas for each raw source (`raw_mta`, `raw_311`, `raw_crashes`). Add validation to `fetch_raw`.
4. Simulate a schema break: rename `ft_mta_subway` to `subway_ridership` in `_fetch_mta`, run the pipeline, observe the error, fix it.
5. Open a PR. Practice self-review. Leave one comment on the diff. Merge.

---

## Module 6 — Testing

### Why it matters
Untested code is a liability that compounds. In ML pipelines, bugs often manifest as
silent quality degradation rather than crashes, making tests even more important.

### Concepts
- Unit tests — test one function in isolation with mocked inputs
- Integration tests — test the full pipeline against real or fixture data
- Regression tests — assert model metrics don't degrade below a threshold
- `pytest` — the standard Python test runner
- Test-driven development (TDD) — write the test first, then the code

### Git practice for this module
Tests live in a `tests/` directory that mirrors `src/`. When you add a new pipeline node,
the PR for that node should include a test for it — **not a separate PR later**.

Practice rebasing: if `main` has moved forward while you were writing tests, you'll
need to rebase your branch to pick up those changes cleanly before merging:

```bash
git fetch origin
git rebase origin/main
# If conflicts: resolve each one, then:
git add <resolved-file>
git rebase --continue
```

Rebasing rewrites your branch's commits on top of the latest `main`, producing a
cleaner history than a merge commit. Use it for feature branches before opening a PR.

**Conflict scenario:** Two test files both define a fixture called `hourly_sample`.
On merge, pytest will find duplicate fixture names. Resolution: rename one to
`hourly_sample_small` and update references. This is a good example of why fixture
files should be organized by domain, not globally.

### Docker connection
Tests should be runnable inside the container — this is what CI will do.
Add a `make test` target that runs:
```bash
docker compose run --rm pipeline pytest tests/ -v
```

The `--rm` flag removes the container after the test run. This is good hygiene —
don't leave one-off containers sitting around.

Update the cron job to run a smoke test after each inference run. If it fails,
log an error. Add to `run_inference_only.sh`:
```bash
# After kedro run --pipeline inference:
python -c "import json; d=json.load(open('data/03_primary/predictions.json')); assert 'precip' in d" \
  && echo "Smoke test passed" \
  || echo "ERROR: Smoke test failed — predictions.json malformed"
```

### Problem set
1. Create `tests/test_data_engineering.py`. Write a unit test for `merge_features` using synthetic DataFrames (3-day NYISO, 2-day MTA). Assert correct columns and lag shift.
2. Write a unit test for `_fetch_mta` by mocking the HTTP call with `pytest-mock`. Assert the pivot is correct given a known fixture response.
3. Write a regression test: load `hourly_features.parquet`, run inference, assert temporal test AUC-ROC for precipitation > 0.65.
4. Configure `.pre-commit-config.yaml` to run `pytest tests/` before every commit.
5. Add the smoke test to `run_inference_only.sh`. Rebase your branch onto the latest `main`. Open a PR, verify `make test` passes, merge.

---

## Module 7 — CI/CD with GitHub Actions

### Why it matters
Manual deployments are error-prone. CI/CD automates testing on every push and
deployment on every merge to `main` — so you always know the code works and the
production system is current.

### Concepts
- CI (Continuous Integration) — run tests automatically on every push/PR
- CD (Continuous Deployment) — deploy automatically when CI passes
- GitHub Actions — YAML workflows in `.github/workflows/`
- GitHub Secrets — credentials injected at runtime, never in code

### Git practice for this module
CI is itself code — treat `.github/workflows/` files with the same discipline as
`src/`. Always test a workflow change on a branch before merging:

```bash
git checkout -b feature/add-ci
# edit .github/workflows/ci.yml
git push origin feature/add-ci
# GitHub will run the workflow on your branch — check the Actions tab
# Only merge once the workflow passes on the branch
```

**Conflict scenario:** Two branches both add new workflow files with the same job name
(`test`). Git won't conflict because they're in separate files, but GitHub Actions will
run both — resulting in duplicate CI runs. Convention: prefix job names with the
feature area (`test-data-engineering`, `test-data-science`) to prevent collisions.

**Branch protection + CI:** Now that you have CI, go back to the branch protection
rule from Module 1 and add "require status checks to pass before merging". Select
your new CI job. From this point on, no PR can merge unless tests pass.

### Docker and cron connection
CD for this project means: when `main` is updated, automatically rebuild the Docker
image and restart the containers. Add this to `.github/workflows/cd.yml`:

```yaml
- name: Rebuild and restart containers
  run: |
    cd ~/code/project-weather-dumb
    git pull origin main
    docker compose build
    docker compose up -d
```

The cron job doesn't need to change — it still calls `docker exec`. But now,
deployments are automatic: merge a PR → CI passes → CD rebuilds the image →
containers restart with the new code → cron picks it up on the next run.

### Problem set
1. Create `.github/workflows/ci.yml` that runs on every push: checkout, Python 3.12, `pip install -e .`, `pytest tests/`, report status.
2. Add `ruff` linting to CI. Fix any issues it finds. Configure `ruff` in `pyproject.toml`.
3. Create `.github/workflows/cd.yml` that runs on push to `main` only: SSH into your server and run `git pull && docker compose build && docker compose up -d`.
4. Add a GitHub Action that posts a PR comment showing the diff in `parameters.yml`. Reviewers should always see when hyperparameters changed.
5. Enable branch protection requiring CI to pass. Attempt to push directly to `main` — verify it's rejected. Open a PR instead, watch CI run, merge.

---

## Module 8 — Model Versioning & Experiment Tracking

### Why it matters
Without tracking, you can't answer: "Which model is in production? What data was it
trained on? Was last week's model better?" Reproducibility is a first-class requirement.

### Concepts
- Model registry — a store of trained models with metadata (when, on what data, what metrics)
- Experiment tracking — log every training run: parameters, metrics, artifacts
- MLflow — open source experiment tracker, runs locally or hosted
- Kedro-MLflow — integrates MLflow into Kedro automatically

### Git practice for this module
Experiment tracking and git complement each other. A good discipline:

- Each experiment run is tagged in git: `git tag experiment/subsample-0.2-2026-04-03`
- The MLflow run ID is stored in the commit message or tag annotation
- This way, you can always go back to the exact code that produced a given model

```bash
git tag -a experiment/baseline -m "MLflow run ID: abc123 | AUC-ROC precip: 0.71"
git push origin --tags
```

**Conflict scenario:** Two branches both modify `train_and_evaluate` in `nodes.py` —
one adds MLflow logging, one adds a new metric. This is a true code conflict.
Resolution strategy: apply the MLflow logging first (it's additive), then add the
new metric inside the already-modified function. Test that both changes work together
before committing the resolution.

### Docker and cron connection
MLflow stores artifacts locally in `mlruns/`. Add it to the `docker-compose.yml`
bind mounts so experiment data persists across container rebuilds:

```yaml
volumes:
  - ./data:/app/data
  - ./logs:/app/logs
  - ./mlruns:/app/mlruns    # ← add this
```

Also add `mlruns/` to `.gitignore` — you don't want to commit gigabytes of model
artifacts. But you do want them to survive a `docker compose down && docker compose up`.

Update the nightly cron job to also start the MLflow UI as a background process,
so you can always browse experiment history:
```bash
# In run_pipeline.sh, after training:
mlflow ui --host 0.0.0.0 --port 5000 &
```

Or add it as a third service in `docker-compose.yml`:
```yaml
mlflow:
  image: ghcr.io/mlflow/mlflow
  ports: ["5000:5000"]
  volumes: ["./mlruns:/mlflow/mlruns"]
  command: mlflow server --host 0.0.0.0 --backend-store-uri /mlflow/mlruns
```

### Problem set
1. Install `mlflow` and `kedro-mlflow`. Run `kedro mlflow init`.
2. Instrument `train_and_evaluate` to log: `train_end`, `val_end`, `train_subsample_frac`, XGBoost hyperparameters, and all evaluation metrics.
3. Run training 3 times with `train_subsample_frac` = 0.1, 0.2, 1.0. Open MLflow UI and compare. Tag the best run in git.
4. Add the `mlruns/` bind mount to `docker-compose.yml`. Rebuild. Verify MLflow data survives `docker compose down && docker compose up -d`.
5. Register the best model in the MLflow registry. Update inference to load from the registry. Open a PR — the diff in `nodes.py` should be small and clear.

---

## Module 9 — Monitoring & Alerting in Production

### Why it matters
Models degrade silently. Data sources go down. Cron jobs fail without telling anyone.
Production systems need automated eyes watching for problems.

### Concepts
- Data drift — input distributions change, making training stale
- Model drift — prediction distribution changes (more "rainy" than expected)
- Alerting — Slack/email notifications when something breaks
- Health checks — a lightweight signal that says "I am alive and last ran at X"

### Git practice for this module
Monitoring code is often written quickly under pressure ("the pipeline is broken, fix it now")
and tends to accumulate tech debt. Practice writing it with the same discipline as
production code:

```bash
git checkout -b feature/monitoring
# Write monitor.py, add tests for it, open a PR
```

Specifically: write a unit test for `monitor.py` before writing `monitor.py`.
This forces you to define clearly what "unhealthy" means before you write the
detection logic — a good habit.

**Conflict scenario:** The `run_inference_only.sh` script is modified on two branches —
yours adds a monitoring call at the end, another branch adds a different post-run check.
Both edits are at the end of the same file. Git will likely conflict on the last few lines.
Resolution: keep both checks, in a logical order (smoke test first, then monitoring).
Add a comment block separating them.

### Docker and cron connection
The monitoring script should run on a schedule — but less frequently than inference.
Add a new cron entry to check health every 15 minutes:

```bash
# Health check every 15 minutes
*/15 * * * * docker exec weather-pipeline python /app/monitor.py >> /home/you/code/project-weather-dumb/logs/monitor.log 2>&1
```

Also add a `healthcheck` to both services in `docker-compose.yml`:
```yaml
# weather-web:
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8501"]
  interval: 60s
  timeout: 10s
  retries: 3
  start_period: 30s

# weather-pipeline:
healthcheck:
  test: ["CMD", "python", "-c", "import json; json.load(open('/app/data/03_primary/predictions.json'))"]
  interval: 5m
  timeout: 10s
  retries: 2
```

Docker will now automatically restart containers that fail their health check.
Run `docker compose ps` to see health status.

### Problem set
1. Write `monitor.py` that reads `predictions.json` and `logs/cron.log` and alerts (stderr or Slack webhook) if: prediction timestamp > 3h old, confidence is "low" 3 consecutive times, or cron log shows failure.
2. Add a `/health` endpoint to the Streamlit app returning `{"status": "ok", "last_inference": "...", "features_age_hours": 1.2}`.
3. Implement a drift check node: compare last 7 days feature means/stds against training distribution (stored as JSON at train time). Log WARNING if any feature drifts >2 std.
4. Add the monitoring cron entry and both Docker healthchecks. Rebuild and restart. Run `docker compose ps` to confirm health status shows `healthy`.
5. Open a PR. The diff should touch: `monitor.py`, `app/app.py`, `docker-compose.yml`, crontab instructions in `PRODUCTION.md`, and a new test file. Verify CI passes.

---

## Module 10 — Infrastructure as Code & Reproducible Environments

### Why it matters
Clicking through UIs to set up servers is not reproducible. If your machine dies,
you want to rebuild the system from code in under an hour. IaC makes your infrastructure
as reviewable and version-controlled as your Python code.

### Concepts
- Docker Compose — defines your multi-container environment as code
- Environment parity — dev, staging, prod should be as identical as possible
- Makefile as interface — one command to build, run, test
- Secrets at runtime — never baked into images; injected via environment variables

### Git practice for this module
Infrastructure changes are high-risk — a bad Docker config can take down production.
Always use a feature branch and test the full stack before merging:

```bash
git checkout -b feature/infra-staging
# Make docker-compose changes
docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d
# Verify everything works
# Only then open a PR
```

**Conflict scenario:** Two branches both modify `docker-compose.yml` — one adds
a new service (`mlflow`), one adds healthchecks. These edits are in the same file
but different sections. Git may or may not conflict depending on proximity. Even if
git merges cleanly, validate the resulting `docker-compose.yml` with:
```bash
docker compose config   # validates and prints the resolved config
```
Always run this after resolving a `docker-compose.yml` conflict before `docker compose up`.

**Cron audit:** By this point your crontab has grown across multiple modules.
Create `cron/crontab.txt` in the repo — a version-controlled record of all cron entries.
Document each job with a comment. This file is the source of truth; when setting up
a new machine, `crontab cron/crontab.txt` installs all jobs at once.

```bash
# cron/crontab.txt
# Hourly inference (fast: data + inference)
5,35 * * * * docker exec weather-pipeline /app/run_inference_only.sh >> /home/you/code/project-weather-dumb/logs/cron.log 2>&1

# Nightly retrain at 02:00
0 2 * * * docker exec weather-pipeline /app/run_pipeline.sh >> /home/you/code/project-weather-dumb/logs/cron.log 2>&1

# Health monitoring every 15 minutes
*/15 * * * * docker exec weather-pipeline python /app/monitor.py >> /home/you/code/project-weather-dumb/logs/monitor.log 2>&1

# Weekly log rotation
0 0 * * 0 mv /home/you/code/project-weather-dumb/logs/cron.log /home/you/code/project-weather-dumb/logs/cron.log.$(date +\%Y\%W)
```

### Problem set
1. Add Docker healthchecks to both services (from Module 9 if not done). Verify `docker compose ps` shows `healthy`.
2. Create `docker-compose.staging.yml` that overrides `train_subsample_frac: 0.05` and `start_date` to 1 year ago. Test the full pipeline in staging: `docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d`.
3. Create `cron/crontab.txt` with all cron entries documented. Add `make install-cron` to the Makefile that runs `crontab cron/crontab.txt`. Test it.
4. Write `bootstrap.sh`: on a fresh Ubuntu machine (test in `docker run -it ubuntu:22.04 bash`), this script installs Docker, clones the repo, builds the image, starts containers, and installs cron. One command to full production.
5. Open a PR. Run `docker compose config` on the resolved config before merging. Update `PRODUCTION.md` with the new `cron/crontab.txt` workflow. Merge.

---

## Module 11 — pytest Deep Dive: Writing and Structuring Tests

### Why it matters

Module 6 introduced testing as a concept. This module goes deeper into pytest mechanics —
how to write tests that are fast, readable, maintainable, and actually catch the bugs
that matter. A test suite that's slow, fragile, or hard to read gets disabled or ignored.
A well-written test suite is a force multiplier on everything else in this guide.

---

### Project structure

```
tests/
    __init__.py               # makes tests/ a Python package
    conftest.py               # shared fixtures loaded automatically by pytest
    test_data_engineering.py  # tests for merge_features and related nodes
    test_inference.py         # tests for run_inference
    test_qc.py                # tests for run_qc (problem set exercise)
```

Pytest discovers any file matching `test_*.py` or `*_test.py`. Inside those files, any
function starting with `test_` is collected and run. That's the full convention.

---

### Fixtures

Fixtures are the most important pytest concept. They are reusable setup functions,
declared with `@pytest.fixture` and injected by name into test arguments.

**Where to put fixtures:**
- `conftest.py` — available to all test files in the same directory and below, automatically
- Inside a test file — available only within that file
- Multiple `conftest.py` files can exist at different directory levels; pytest merges them

**In this repo** (`tests/conftest.py`):

```python
@pytest.fixture
def fake_hourly():
    rng = np.random.default_rng(42)          # fixed seed → deterministic
    idx = pd.date_range("2024-01-01", periods=200, freq="h")
    return pd.DataFrame({
        "ft_nyiso_load_mw":    rng.uniform(3000, 8000, 200),
        "ft_mta_subway":       rng.uniform(1e6,   5e6, 200),
        ...
    }, index=idx)

@pytest.fixture
def fake_model_precip(fake_hourly):     # fixtures can depend on other fixtures
    return _tiny_xgb(fake_hourly[_FEAT_COLS], 4)
```

Key design decisions in the repo's fixtures:
- **Fixed seed (`42`)** — random data but deterministic. Tests never flap due to random variation.
- **Tiny model (`n_estimators=5`, `max_depth=2`)** — builds in milliseconds. No need to cache it.
- **Synthetic data only** — no network calls, no parquet files. Tests run offline, in CI, inside Docker.
- **Fixture composition** — `fake_model_precip` receives `fake_hourly` as an argument. Pytest resolves
  the dependency graph automatically. You never call fixtures directly.

**Fixture scope** — by default, fixtures run fresh per test. Use `scope="module"` or `scope="session"`
if setup is expensive and safe to share:

```python
@pytest.fixture(scope="session")
def big_dataframe():
    return pd.read_parquet("data/02_intermediate/hourly_features.parquet")
```

---

### What to test: contracts, not internals

The most common mistake is testing implementation details — the internal logic of a function.
Good tests assert **contracts**: what goes in, what must come out.

**Implementation test (fragile):**
```python
def test_merge_uses_left_join():
    # Tests that merge_features internally calls .join(how="left") — breaks if we refactor
    with patch("pandas.DataFrame.join") as mock_join:
        merge_features(...)
        mock_join.assert_called_with(..., how="left")
```

**Contract test (robust):**
```python
def test_merge_preserves_nyiso_length():
    # Tests the observable contract: output has same row count as NYISO input
    result = merge_features(nyiso, openmeteo, empty, empty, empty, ...)
    assert len(result) == len(nyiso)
```

The contract test survives any internal refactor. It fails only when the behavior changes.

**The contracts we test in this repo:**

For `merge_features`:
- Output length matches NYISO input length
- `ft_nyiso_delta_3h` always appears
- Delta values match `load.diff(3)` exactly
- Works when all optional sources are empty
- MTA values absent before lag window, present after

For `run_inference`:
- Output dict has the required top-level keys
- Predicted classes are valid labels (not arbitrary strings)
- Confidence is one of three valid buckets
- Probabilities sum to 1.0 (within floating point tolerance)
- SHAP keys match the feature columns used
- Uses the most recent non-null row
- Falls back correctly when recent rows are NaN
- Unknown `feature_cols` entries don't crash

---

### Parameterized tests

When the same test logic applies to multiple inputs, use `@pytest.mark.parametrize` instead
of copy-pasting tests or looping inside a test:

```python
# Before: one test, a loop inside
def test_confidence_is_valid_bucket(fake_hourly, fake_model_precip, fake_model_temp):
    result = _run(fake_hourly, fake_model_precip, fake_model_temp)
    for target in ("precip", "temp"):
        assert result[target]["confidence"] in ("high", "medium", "low")

# After: parametrized — each target gets its own row in pytest -v output
@pytest.mark.parametrize("target", ["precip", "temp"])
def test_confidence_is_valid_bucket(fake_hourly, fake_model_precip, fake_model_temp, target):
    result = _run(fake_hourly, fake_model_precip, fake_model_temp)
    assert result[target]["confidence"] in ("high", "medium", "low")
```

The `-v` output now shows:
```
test_inference.py::test_confidence_is_valid_bucket[precip] PASSED
test_inference.py::test_confidence_is_valid_bucket[temp]   PASSED
```

Each parameter combination is a separate test. If `precip` fails and `temp` passes,
you see exactly which one — not just "the loop failed somewhere."

Multi-dimensional parametrize:
```python
@pytest.mark.parametrize("lag,source", [
    (3, "mta"),
    (2, "311"),
    (5, "crashes"),
])
def test_lag_applied(lag, source):
    ...
```

---

### Markers

Use `@pytest.mark` to tag tests and run subsets:

```python
@pytest.mark.slow
def test_full_inference_pipeline():
    ...  # takes 30+ seconds

@pytest.mark.smoke
def test_predictions_json_is_valid():
    ...  # fast sanity check
```

Register markers in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = [
    "slow: tests that take more than 5 seconds",
    "smoke: fast sanity checks suitable for pre-commit",
]
```

Run subsets:
```bash
pytest tests/ -m smoke           # only smoke tests (fast)
pytest tests/ -m "not slow"      # everything except slow tests
pytest tests/ -m "slow and smoke"
```

Practical use in this repo:
- Pre-commit hook runs only `smoke` tests (< 5 seconds total)
- CI runs all tests including `slow` (35 seconds is fine in CI)
- `docker compose run pipeline pytest tests/ -m smoke` is your fast sanity check before a deploy

---

### Testing edge cases and failure modes

The most valuable tests are the ones that test what happens when things go wrong:

```python
def test_skips_trailing_null_rows(fake_hourly, fake_model_precip, fake_model_temp):
    """When recent rows are NaN, inference must fall back to the last complete row."""
    df = fake_hourly.copy()
    df.iloc[-5:] = float("nan")           # simulate stale data from source lag
    result = _run(df, fake_model_precip, fake_model_temp)
    assert result["timestamp"] == str(df.index[-6])   # -6th row, not -1st
```

This test exists because the inference node has a specific behavior contract:
`hourly_features[feat].dropna().iloc[[-1]]` — take the most recent non-null row.
If someone changes this to `iloc[[-1]]` (removes the dropna), this test catches it.

Pattern for edge case tests in this repo:
- Empty optional sources (`_empty()`) — all optional sources can be absent
- Unknown feature columns — `feature_cols` entries not in the DataFrame are silently dropped
- Trailing NaN rows — fall back gracefully
- Wrong-indexed openmeteo stub — caused 3 test failures during development (documented in the pytest module in `TRAINING.md`)

---

### The openmeteo stub lesson

During development of `test_data_engineering.py`, three tests failed not because the code
was wrong, but because the test stub was wrong.

`merge_features` first does:
```python
hourly = raw_nyiso.join(raw_openmeteo, how="left")
```

Passing `pd.DataFrame()` (RangeIndex, 0 rows) as the openmeteo stub caused `join` to
produce 0 rows — because joining a DatetimeIndex DataFrame to a RangeIndex DataFrame
on mismatched index types results in an empty output.

Fix: match the structural contract of the real data (DatetimeIndex, matching frequency),
even if the content is empty:

```python
def _openmeteo(n: int = 200) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame(index=idx)   # correct index type, no columns
```

**Rule:** When writing a stub, ask: what structural properties must this stub satisfy
for the function under test to behave normally? Index type, column names, dtypes, and
frequency are all structural — they affect join behavior, reindex behavior, and
column selection even before any logic runs.

---

### Running the test suite

```bash
# All tests, verbose
.venv/bin/pytest tests/ -v

# One file
.venv/bin/pytest tests/test_inference.py -v

# One test by keyword
.venv/bin/pytest tests/ -k "lag" -v

# Stop on first failure (fast feedback during development)
.venv/bin/pytest tests/ -x

# Show local variables on failure (useful for debugging)
.venv/bin/pytest tests/ -l

# Run only fast tests
.venv/bin/pytest tests/ -m smoke

# Show slowest 5 tests
.venv/bin/pytest tests/ --durations=5
```

Expected baseline: 15 tests, ~35 seconds (SHAP computation dominates — hence the `slow` marker case for SHAP-heavy tests).

---

### Git practice for this module

Tests and the code they test belong in the **same PR**. Never merge a new node without
a test for it, and never merge a test for dead code.

```bash
git checkout -b feature/pipeline-tests
# Write tests alongside the code they test
pytest tests/ -v   # all green before pushing
git add tests/ pyproject.toml
git commit -m "Add pytest suite for data_engineering and inference"
git push -u origin feature/pipeline-tests
```

**Rebase before merging.** If `main` has moved since you branched:
```bash
git fetch origin
git rebase origin/main
# Resolve any conflicts, then:
git add <resolved>
git rebase --continue
```

**Conflict scenario:** Two branches both add fixtures to `conftest.py` — one adds
`fake_model_precip`, another adds `fake_hourly_small`. Git resolves the file without
conflict. But if both fixtures have the same name (e.g. both add `fake_hourly`),
pytest will complain at collection time. Rule: fixture names are global within a
`conftest.py` scope — treat them like public API names and coordinate with branches.

---

### Docker connection

Tests should run inside the same environment as production. Two patterns:

**Run-time test (during development):**
```bash
docker compose run --rm pipeline pytest tests/ -v
```

**Build-time test (baked into CI-like Docker build):**
```dockerfile
# In Dockerfile, after pip install:
COPY tests/ tests/
RUN pytest tests/ -v --tb=short
```

This makes `docker compose build` fail if any test fails — you catch environment
regressions (missing system library, wrong package version) before the image ships.

For a leaner production image, use multi-stage:
```dockerfile
FROM base AS test
COPY tests/ tests/
RUN pytest tests/ -v

FROM base AS production
# tests/ never copied — lean final image
```

---

### Problem set

**P1 — 311 lag test.** The 311 source has a 2-day lag (`lag_311: 2`). Write
`test_311_lag_shifts_data` in `test_data_engineering.py` following the same pattern as
`test_mta_lag_shifts_data`. Build a minimal 311 fixture with `ft_311_heat` only.
Assert values are absent in the first `2 * 24` hours and present after.

**P2 — QC node tests.** The `feature/inference-qc` branch added `run_qc` in
`src/weather/pipelines/inference/nodes.py`. Write `tests/test_qc.py` covering:
- A prediction with `timestamp = now` returns `qc.overall == "pass"`
- A prediction with timestamp 24h ago returns `qc.overall == "warn"`
- A prediction with timestamp 72h ago returns `qc.overall == "fail"`
- A prediction missing one feature from its `features` dict reports it in `missing`
- A prediction missing 3 of 10 features returns `qc.overall == "fail"` (coverage < 80%)

**P3 — Parametrize.** In `test_inference.py`, rewrite `test_confidence_is_valid_bucket`
and `test_probabilities_sum_to_one` using `@pytest.mark.parametrize("target", ["precip", "temp"])`.
Compare the `-v` output before and after — each target should now appear as a separate test row.

**P4 — Markers.** Tag every test that constructs a model (calls `_tiny_xgb`) with
`@pytest.mark.slow`. Tag the rest with `@pytest.mark.smoke`. Register both markers in
`pyproject.toml`. Verify:
```bash
pytest tests/ -m smoke --durations=5   # should finish in < 5 seconds
pytest tests/ -m slow                  # should include all SHAP-heavy tests
```

**P5 — Pre-commit hook.** Install `pre-commit`. Create `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: local
    hooks:
      - id: pytest-smoke
        name: pytest smoke tests
        entry: .venv/bin/pytest tests/ -m smoke -q
        language: system
        pass_filenames: false
        stages: [pre-commit]
```
Run `pre-commit install`. Break a smoke test, attempt a commit, observe the block, fix it.
The hook runs only smoke tests — fast enough to not slow down commits.

**P6 — Coverage.** Install `pytest-cov`. Run:
```bash
pytest tests/ --cov=src/weather --cov-report=term-missing
```
Identify the two functions with the lowest coverage. Write one new test for each.
Coverage is a guide, not a target — don't write tests just to hit 100%.

---

## Capstone — The Full MLOps Loop

By this point you have:
- A clean branching workflow with PR templates and protected `main` (Module 1)
- Pinned dependencies and a Makefile (Module 2)
- Environment-layered config with secrets management (Module 3)
- Structured JSON logging and feature validation nodes (Module 4)
- Pandera schemas as pipeline contracts (Module 5)
- A test suite with unit, integration, and regression tests (Module 6)
- CI running on every push, CD on merge to `main` (Module 7)
- MLflow tracking all training runs with git tags (Module 8)
- Monitoring, alerting, and Docker healthchecks (Module 9)
- Reproducible infrastructure with a staging environment (Module 10)

**Final project:** Introduce a new data source — borough-level 311 crashes, additional
311 complaint types, or Citi Bike snapshot collection. Do it the full production way:

1. Open an issue on GitHub describing the feature and its expected signal
2. Create a feature branch from `main`
3. Write the pandera schema and unit test **before** writing the fetch function (TDD)
4. Implement the fetch function with structured logging and error handling
5. Add the feature to `parameters.yml` with an inline comment
6. Run training, log to MLflow, compare against baseline with a git tag
7. Open a PR — CI must pass, `parameters.yml` diff shown, PR template filled out
8. Merge via PR (not direct push — branch protection enforces this)
9. CD automatically rebuilds the Docker image and restarts containers
10. Monitor the first 24 hours: check `monitor.log`, check MLflow for drift, check `docker compose ps` for health
11. Update `cron/crontab.txt` if any scheduling changed

This is the full loop. Every step traces back to a module. That's the point.

---

## Reference: Key Commands

```bash
# Git
git checkout -b feature/my-feature
git push origin feature/my-feature
git fetch origin && git rebase origin/main   # sync with main before PR
git log --oneline --graph                    # visualize branch history
git tag -a experiment/name -m "MLflow run: abc123"
git push origin --tags
docker compose config                        # validate compose file after conflict

# Testing
pytest tests/ -v
pytest tests/ -k "test_mta"
docker compose run --rm pipeline pytest tests/ -v

# Linting
ruff check src/
ruff format src/

# MLflow
mlflow ui --host 0.0.0.0 --port 5000
kedro run --pipeline data_science

# Docker
docker compose up -d
docker compose ps                            # check health status
docker compose logs -f
docker compose build
docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d
docker compose config                        # validate before applying

# Cron
crontab cron/crontab.txt                     # install all jobs from file
crontab -l                                   # verify installed jobs
tail -f logs/cron.log

# Kedro
kedro run
kedro run --pipeline data_engineering
kedro run --pipeline inference
kedro viz
```
