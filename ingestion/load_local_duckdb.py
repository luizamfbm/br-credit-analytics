"""Load SCR.data CSVs into a local DuckDB file, mirroring the Snowflake RAW table.

Used for local development and CI, so the dbt project can run without a cloud account.

Examples
--------
python ingestion/load_local_duckdb.py data/raw/scr_data            # every CSV under the folder
python ingestion/load_local_duckdb.py ci/sample/scrdata_sample.csv  # the CI sample

Idempotent: rows from a file are deleted before the file is loaded again.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

COLUMNS = [
    "data_base", "uf", "segmento", "cliente", "cnae_ocupacao", "porte", "modalidade",
    "submodalidade", "origem", "indexador", "numero_de_operacoes",
    "a_vencer_ate_90_dias", "a_vencer_de_91_ate_360_dias", "a_vencer_de_361_ate_1080_dias",
    "a_vencer_de_1081_ate_1800_dias", "a_vencer_de_1801_ate_5400_dias", "a_vencer_acima_de_5400_dias",
    "carteira_a_vencer", "vencido_de_15_ate_90_dias", "vencido_acima_de_90_dias", "carteira_vencida",
    "carteira_ativa", "carteira_inadimplencia", "ativo_problematico",
]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paths", nargs="+", help="CSV files or folders")
    p.add_argument("--db", default="data/credito.duckdb")
    args = p.parse_args(argv)

    files: list[Path] = []
    for raw in args.paths:
        path = Path(raw)
        files += sorted(path.rglob("*.csv")) if path.is_dir() else [path]
    if not files:
        print("No CSV files found", file=sys.stderr)
        return 1

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(args.db)
    con.execute("create schema if not exists raw")
    cols_ddl = ", ".join(f"{c} varchar" for c in COLUMNS)
    con.execute(f"create table if not exists raw.scr_data ({cols_ddl}, _source_file varchar, _loaded_at timestamp)")

    col_types = "{" + ", ".join(f"'{c}': 'VARCHAR'" for c in COLUMNS) + "}"
    for f in files:
        name = f.name
        con.execute("delete from raw.scr_data where _source_file = ?", [name])
        con.execute(
            f"""
            insert into raw.scr_data
            select {", ".join(COLUMNS)}, ? as _source_file, current_timestamp as _loaded_at
            from read_csv(?, delim=';', quote='"', header=true, columns={col_types})
            """,
            [name, str(f)],
        )
        n = con.execute("select count(*) from raw.scr_data where _source_file = ?", [name]).fetchone()[0]
        print(f"{name}: {n:,} rows loaded")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
