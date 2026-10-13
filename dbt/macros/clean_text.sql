{#
  Standardizes the text columns of SCR.data:
    * the BCB files contain a stray Windows-1252 dash (U+0096) in some values -> "-"
    * repeated spaces, e.g. "Financiamentos rurais  (ex-..." -> single space
    * leading/trailing spaces, e.g. "Comercialização " -> trimmed
  Dispatched because DuckDB's regexp_replace needs the 'g' flag to replace every match.
#}
{% macro clean_text(column) -%}
    {{ return(adapter.dispatch('clean_text')(column)) }}
{%- endmacro %}

{% macro default__clean_text(column) -%}
    trim(regexp_replace(replace({{ column }}, chr(150), '-'), ' +', ' '))
{%- endmacro %}

{% macro duckdb__clean_text(column) -%}
    trim(regexp_replace(replace({{ column }}, chr(150), '-'), ' +', ' ', 'g'))
{%- endmacro %}
