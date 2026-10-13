{#
  Converts Brazilian-formatted numbers ("159931,83") to DECIMAL(20,2).
  The BCB files use a comma as decimal separator and no thousands separator.
#}
{% macro br_number(column) -%}
    cast(replace({{ column }}, ',', '.') as decimal(20, 2))
{%- endmacro %}
