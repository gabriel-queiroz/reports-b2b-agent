# Regras gerais do catálogo

Valem para qualquer tabela. Colunas, aliases, partição, filtros padrão e enums de cada tabela estão no schema dela (`get_table_schema`).

## Aliases em PT-BR

**TODAS as queries geradas DEVEM usar os aliases em português brasileiro listados em cada tabela.**

Exemplo correto:
```sql
SELECT
  e.id AS id_colaborador,
  e.name AS nome_colaborador,
  e.email AS email_colaborador,
  e.created_at AS data_criacao_colaborador,
  c.company_group_id AS company_group_id
FROM main.ifoodoffice_management_silver.employee e
INNER JOIN fintech_companies.companies c ON e.company_id = c.company_id
WHERE e.deleted = false
  AND c.company_group_id = '<uuid-do-grupo>'
```

**⚠️ IMPORTANTE**: Os nomes entre `SELECT ... FROM` (id, name, email, created_at) são os nomes reais das colunas na tabela. Os nomes após `AS` (id_colaborador, nome_colaborador, email_colaborador, data_criacao_colaborador) são os aliases em português que aparecem no resultado final.

Isso garante que:
- Os relatórios sejam entregues completamente em português
- Os nomes de campos sejam consistentes e legíveis para usuários brasileiros
- A documentação permaneça alinhada com a implementação

## Filtro por grupo

O filtro por grupo é obrigatório em toda query. A regra de cada tabela está na linha **Multi-tenant** do schema dela; query sem esse filtro é rejeitada.

Além do filtro, toda query deve incluir o `company_group_id` como coluna de saída
no `SELECT` (campo real da tabela, alias exato `company_group_id`).

> Para `financial_account` e `financial_transaction`, o campo de grupo é `group_id`.
> Use esse campo no filtro e exponha-o com o alias exato `company_group_id` — a coluna
> de saída do grupo usa sempre esse alias, sobrepondo o Alias PT-BR da tabela.

## Licenças (separada × unificada)

Regra de negócio conceitual — não é uma tabela, mas define o comportamento do filtro multi-tenant.

- Licença separada: 1 CNPJ ↔ 1 `company_group_id`.
- Licença unificada: 2+ CNPJs ↔ 1 `company_group_id`.
- Consequência: filtrar por `company_group_id` pode retornar múltiplos CNPJs. "Filtrar por grupo" não é o mesmo que "filtrar por CNPJ".
- O filtro de segurança dos relatórios é sempre `company_group_id`/`group_id`. CNPJ é campo de exibição ou filtro auxiliar — nunca filtro de segurança.
- Matriz × filial: hoje NÃO é possível distinguir matriz de filial, pois isso depende de `company_groups.main_company.cnpj` (tabela fora do catálogo). O `company_cnpj` da nota fiscal (`company_tax_invoice.company_cnpj`) pode ser matriz ou filial.

## Enums

Cada arquivo de tabela termina com os valores possíveis das suas colunas (`### Valores possíveis (enums)`); os de produto, usados por várias tabelas, ficam em `_enums_compartilhados.md`. Traduções em **pt-BR** conforme a plataforma Benf Companies. Use os valores **ENUM** (coluna da esquerda) em filtros SQL; use a **Tradução** para labels em relatórios.

## Tipos de dados

- **STRING**: Texto (UUIDs, nomes, CPF/CNPJ)
- **DOUBLE**: Valores monetários com precisão
- **INTEGER/BIGINT**: Números inteiros
- **BOOLEAN**: Verdadeiro/Falso
- **DATE**: Data (YYYY-MM-DD)
- **TIMESTAMP**: Data e hora (ISO 8601)
- **STRUCT**: Dados aninhados (usar `.campo` para expandir)
