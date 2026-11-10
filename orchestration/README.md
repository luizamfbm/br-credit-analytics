# Orchestration (Airflow on Astro)

Two DAGs, defined in one file by `make_dag` ([dags/scr_monthly.py](dags/scr_monthly.py)):

| DAG | Schedule | Source | Target database |
|---|---|---|---|
| `scr_monthly` | manual | `data/replay/landing` (files you "publish" by hand) | `CREDITO_REPLAY` (dbt target `replay`) |
| `scr_bcb_weekly` | Mondays 07:00, São Paulo | BCB site: HEAD request on this year's and last year's ZIPs, download only if changed | `CREDITO` (dbt target `dev`) |

Each run: `detect` (MD5 of each available file vs the latest entry in `RAW.LOAD_LOG`) → `load` (one mapped task per new or revised month, one at a time, delete + `COPY ... FORCE` + log entry in a single transaction) → `dbt_build` (once). A run with nothing new ends as **skipped**.

The DAGs load into Snowflake. Since the Snowflake trial ended, the project runs on DuckDB locally (see the main [README](../README.md#architecture)); the DAG code is kept as it ran.

## Run locally

Needs the [Astro CLI](https://www.astronomer.io/docs/astro/cli/install-cli) and Docker (or Podman).

```bash
cd orchestration
cp ../.env.example .env        # SNOWFLAKE_* values; the key path is the one inside the container:
                               # SNOWFLAKE_PRIVATE_KEY_PATH=/usr/local/airflow/include/keys/dbt_svc_key.p8
astro dev start                # UI at http://localhost:8080
```

`docker-compose.override.yml` mounts `../dbt`, `../ingestion` and `../data` into the scheduler, and the folder with the Snowflake private key (read-only). Change the key folder to your own path. The key itself never goes into the image or the repository.

## Replay a release by hand

```bash
mkdir -p ../data/replay/vault ../data/replay/landing
cp ~/Downloads/scrdata_2026*.csv ../data/replay/vault/      # real files, kept aside
cp ../data/replay/vault/scrdata_202602.csv ../data/replay/landing/   # "publish" February
```

Trigger `scr_monthly` in the UI. Then try a batch (copy several months), the same file again (the run is skipped) and a revised month (edit a value and copy it again: only that month reloads).
