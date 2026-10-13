# Guia passo a passo do projeto

Este guia leva o projeto do zero até ele estar rodando no Snowflake, publicado no GitHub com CI e pronto para entrevista. Os comandos são para macOS (zsh).

**Antes de tudo:** você precisa conseguir explicar cada arquivo deste repositório numa entrevista. Siga os passos na ordem, rode cada comando, abra cada arquivo e leia o comentário do topo. A tabela do passo 10 diz o que cada arquivo faz e qual conceito ele prova.

---

## 1. Preparar a máquina (20 min)

```bash
# Python 3.11 ou mais novo
python3 --version

# Entre na pasta do projeto e crie um ambiente virtual
cd br-credit-analytics
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Variáveis de ambiente: copie o modelo e preencha depois
cp .env.example .env
```

Toda vez que abrir um terminal novo para trabalhar no projeto:

```bash
source .venv/bin/activate
set -a; source .env; set +a
```

## 2. Rodar tudo localmente primeiro, sem nuvem (15 min)

Fazer funcionar local antes de mexer em AWS e Snowflake separa os problemas: se der erro depois, você sabe que é configuração de nuvem, não o modelo.

```bash
# Coloque o CSV de julho/2024 que você já baixou nesta pasta:
mkdir -p data/raw/scr_data/ano=2024/mes=07
cp ~/Downloads/scrdata_202407.csv data/raw/scr_data/ano=2024/mes=07/

# Carrega no DuckDB (um banco que é só um arquivo)
python ingestion/load_local_duckdb.py data/raw/scr_data

# Roda o dbt
cd dbt
export DBT_PROFILES_DIR=.
export DBT_TARGET=local
dbt deps
dbt build
```

**Resultado esperado:** `Done. PASS=48 WARN=0 ERROR=0`. São 2 seeds, 7 models, 1 snapshot e 37 testes.

Para ver a documentação com a linhagem (o desenho de qual tabela depende de qual):

```bash
dbt docs generate && dbt docs serve
```

Tire um print da linhagem: ele vai para o README.

## 3. AWS: bucket e upload (30 min)

1. No console da AWS, crie um bucket na região **sa-east-1 (São Paulo)**, por exemplo `luiza-scr-data`. Deixe o bloqueio de acesso público **ligado**.
2. Crie um usuário IAM só para o upload, com permissão `s3:PutObject` no bucket. Gere a access key e configure no terminal:
   ```bash
   aws configure   # cole a access key, a secret e a região sa-east-1
   ```
   Nunca coloque a chave em arquivo do repositório.
3. No `.env`, preencha `SCR_BUCKET=luiza-scr-data`.
4. Baixe 24 meses e suba para o S3:
   ```bash
   python ingestion/download_scr.py --start 2023-07 --end 2025-06 --bucket $SCR_BUCKET
   ```
   O script baixa um ZIP por ano (pode levar alguns minutos), extrai cada mês e sobe para `s3://<bucket>/raw/scr_data/ano=YYYY/mes=MM/`. O log mostra linhas e MD5 de cada arquivo.

> Se o nome dos arquivos dentro do ZIP do Banco Central for diferente do esperado, o log mostra os nomes encontrados. O script procura qualquer `.csv` com o ano e mês (`202407`) no nome.

## 4. Snowflake: setup e carga (40 min)

1. Crie o trial em [signup.snowflake.com](https://signup.snowflake.com): edição **Standard**, nuvem **AWS**, região **South America (São Paulo)**. Mesma região do bucket = sem custo de transferência.
2. Abra uma worksheet, cole `snowflake/01_setup.sql`, troque `<YOUR_USER>` pelo seu usuário e rode tudo.
3. **Ligar o Snowflake ao S3** (a parte mais chata, faça com calma):
   1. No IAM, crie uma policy com o conteúdo de `aws/s3_read_policy.json` (troque `<BUCKET>`).
   2. Crie uma role chamada `snowflake-scr-read`: tipo "AWS account", sua própria conta, marque "Require external ID" e digite `0000` por enquanto. Anexe a policy.
   3. Copie o ARN da role.
   4. Em `snowflake/02_s3_integration.sql`, troque `<AWS_ACCOUNT_ID>` e `<BUCKET>` e rode até o `desc integration`.
   5. Do resultado, copie `STORAGE_AWS_IAM_USER_ARN` e `STORAGE_AWS_EXTERNAL_ID` para o `aws/trust_policy.json` e cole esse JSON em "Trust relationships" da role.
   6. Rode o resto do `02_s3_integration.sql`. O `list @credito.raw.scr_stage` tem que mostrar seus arquivos.
4. Rode `snowflake/03_copy_into.sql`. A última consulta mostra quantas linhas vieram de cada arquivo (cerca de 300 mil por mês).

Rodar o COPY de novo não duplica nada: o Snowflake lembra quais arquivos já carregou.

## 5. dbt no Snowflake (20 min)

1. No `.env`, preencha as variáveis `SNOWFLAKE_*`. O `SNOWFLAKE_ACCOUNT` fica em Admin → Accounts, no formato `ORGNAME-ACCOUNTNAME`.
2. No `.env`, mude `DBT_TARGET=dev`.
3. Rode:
   ```bash
   set -a; source .env; set +a
   cd dbt && export DBT_PROFILES_DIR=.
   dbt debug    # tem que terminar com "All checks passed!"
   dbt deps
   dbt build
   dbt source freshness
   ```
4. No Snowflake, confira os schemas `STAGING`, `MARTS`, `REPORTING`, `SEEDS` e `SNAPSHOTS`.

**Para provar a carga incremental:** carregue primeiro 22 meses, rode `dbt build`, depois carregue os 2 últimos e rode de novo. No log, o model `fct_credit_portfolio_monthly` processa só os meses novos. Anote os tempos para o README.

**Para provar o SCD tipo 2:** mude o `product_group` de uma linha em `seeds/product_grouping.csv`, rode `dbt seed` e `dbt snapshot`, e consulte `snapshots.snap_product_grouping`: a linha antiga ganha `dbt_valid_to` e aparece uma nova. Depois desfaça a mudança.

## 6. GitHub e CI (30 min)

```bash
cd ..   # raiz do projeto
git init
git add .
git commit -m "Initial commit: ingestion, Snowflake setup and dbt star schema"
git branch -M main
git remote add origin https://github.com/luizamfbm/br-credit-analytics.git
git push -u origin main
```

Crie o repositório antes no GitHub, público, **sem** README (o projeto já tem).

O CI (`.github/workflows/dbt_ci.yml`) roda sozinho a cada push e pull request. Ele usa DuckDB com uma amostra de 2.000 linhas reais, então não precisa de senha nenhuma. Depois do primeiro run verde:

1. Settings → Branches → Add rule para `main` → marque "Require status checks to pass" e escolha `dbt-build`.
2. A partir daí, todo trabalho entra por branch e pull request:
   ```bash
   git checkout -b feat/dashboard-export
   # ... muda arquivos ...
   git add . && git commit -m "Add dashboard export"
   git push -u origin feat/dashboard-export
   ```
   Abra o pull request no GitHub, espere o CI ficar verde e faça o merge.

## 7. Dashboard (meio dia)

Siga `dashboards/README.md`: exporte o `rpt_delinquency_monthly` em CSV, monte as três visões no Tableau Public e cole o link no README. O mesmo CSV serve para o Power BI e o Looker Studio do sprint pós-férias.

## 8. Fase 2: Airflow (novembro)

1. Instale o Astro CLI (`brew install astro`) e o Docker Desktop.
2. Numa pasta separada: `astro dev init`. Copie para dentro dela as pastas `orchestration/dags`, `ingestion`, `snowflake` e `dbt` deste repositório (ou ajuste o caminho `PROJECT_ROOT` na DAG).
3. No `requirements.txt` do projeto Astro: `apache-airflow-providers-snowflake`, `dbt-snowflake`, `requests`, `boto3`.
4. `astro dev start`, abra `localhost:8080`, crie a conexão `snowflake_default` em Admin → Connections e as variáveis de ambiente do `.env`.
5. Rode a DAG `scr_monthly` manualmente com o parâmetro `{"month": "2025-06"}` para testar. Depois teste um backfill de 6 meses.
6. Print da DAG verde no README.

## 9. Fase 3: IA com validação (dezembro)

```bash
# Sem chave de API: o modo mock inclui um número errado de propósito
python ai/monthly_summary.py --month 2024-07 --mock
```

O resultado esperado é 3 afirmações `ok`, 1 `mismatch` e `Publishable: False`. Isso é o validador funcionando.

Com a chave real (`pip install anthropic`, `export ANTHROPIC_API_KEY=...`), rode sem `--mock`. Para o README:

1. Rode para 12 meses.
2. Calcule a média do `claim_accuracy`.
3. Teste dois prompts ou dois modelos e compare.

Hoje o script lê do DuckDB local. Adaptar para ler do Snowflake (com `snowflake-connector-python`) é um bom exercício e mais uma linha de CV.

## 10. O que cada arquivo faz (para a entrevista)

| Arquivo | O que faz | Conceito que prova |
|---|---|---|
| `ingestion/download_scr.py` | Baixa, extrai e sobe cada mês para o S3 | Ingestão idempotente, particionamento por data, auditoria (linhas + MD5) |
| `ingestion/load_local_duckdb.py` | Carrega os CSVs num DuckDB local | Ambiente local reproduzível, CI sem nuvem |
| `snowflake/01_setup.sql` | Warehouse, database, schemas, role e tabela RAW | Arquitetura em camadas, menor privilégio, controle de custo (auto_suspend) |
| `snowflake/02_s3_integration.sql` | Liga o Snowflake ao S3 sem chave de acesso | Storage integration, IAM role com external ID |
| `snowflake/03_copy_into.sql` | Carga do S3 para a RAW | COPY INTO idempotente, metadados de linhagem |
| `dbt/macros/clean_text.sql` | Limpa texto, com versão para Snowflake e DuckDB | Macros, adapter.dispatch (SQL entre bancos diferentes) |
| `dbt/macros/br_number.sql` | Converte "1234,56" em número | Padronização na camada de staging |
| `dbt/models/staging/stg_scr__credit_portfolio.sql` | Renomeia, tipa, limpa e deduplica | Staging sem regra de negócio, QUALIFY, tratamento do -1 |
| `dbt/models/marts/dim_*.sql` | As cinco dimensões | Star schema, surrogate keys, junk dimension |
| `dbt/models/marts/fct_credit_portfolio_monthly.sql` | Tabela fato | Periodic snapshot, grão declarado, carga incremental |
| `dbt/models/reporting/rpt_delinquency_monthly.sql` | Tabela pronta para o painel | Taxa calculada depois da agregação |
| `dbt/tests/*.sql` | Testes de reconciliação e completude | Qualidade de dados como código |
| `dbt/seeds/*.csv` | Regiões e agrupamento de produtos | Dados de referência versionados |
| `dbt/snapshots/snapshots.yml` | Histórico do agrupamento | SCD tipo 2 |
| `.github/workflows/dbt_ci.yml` | Roda tudo a cada pull request | CI/CD para dados |
| `orchestration/dags/scr_monthly.py` | Orquestra o mês inteiro | Airflow, data interval, backfill, retries |
| `ai/monthly_summary.py` | Resumo por LLM com validação de cada número | Avaliação de LLM contra fonte de verdade |

## 11. Problemas comuns

| Sintoma | Causa provável |
|---|---|
| `dbt debug` falha na conexão | `SNOWFLAKE_ACCOUNT` no formato errado, ou esqueceu o `source .env` |
| `list @stage` vazio ou com erro de acesso | Trust policy da role sem o external ID certo, ou bucket diferente em `storage_allowed_locations` |
| COPY carregou 0 linhas | Arquivos já carregados antes (normal) ou `pattern` não bate com o nome dos arquivos |
| Teste `not_null_dim_product_product_group` falhou | O Banco Central publicou uma submodalidade nova: adicione a linha em `seeds/product_grouping.csv` |
| `dbt deps` falha | Sem internet ou versão do dbt antiga: rode `pip install -r requirements.txt` de novo |
| Trial do Snowflake acabou | Cadastre o cartão e mantenha o warehouse X-Small com auto_suspend |

## 12. Antes de divulgar

- [ ] Atualize o "Example finding" do README com números do histórico completo, conferidos por você
- [ ] Print da linhagem do dbt docs e link do Tableau no README
- [ ] CI verde no GitHub
- [ ] Nenhuma senha ou chave em nenhum arquivo (`git log -p | grep -i password` não pode achar nada)
- [ ] Atribuição do Banco Central e licença ODbL no README (já está)
