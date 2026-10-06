# Catálogo de tabelas do Databricks — um arquivo por tabela

Fonte: https://ifood.atlassian.net/wiki/spaces/IFE/pages/6599770142/Tabelas+do+Databricks

Substitui o antigo `data/schema.md`. **Esta pasta é lida por código** (`catalog.py`), não é só documentação.

## Arquivos

- `<tabela>.md` — um por tabela, com o nome físico (último trecho do `**Local**`). É o que a tool `get_table_schema` devolve ao agente.
- `_relacionamentos.md` — chaves de JOIN no formato `tabela.coluna ──> tabela.coluna`. O `sql_guard` só aceita `JOIN ... ON` por elas, e o arquivo entra inteiro no prompt (junto com o índice gerado por `build_tables_index`).
- `_regras_gerais.md` — regras que valem para qualquer tabela (aliases PT-BR, coluna de grupo na saída, licenças, tipos).
- `_enums_compartilhados.md` — enums de colunas presentes em várias tabelas. O bloco é anexado ao schema de toda tabela que tiver uma das colunas citadas no título.
- Arquivo que começa com `_` não é tabela.

## O que o `catalog.py` lê de cada arquivo de tabela

- `## N. Nome (Título)` — N é a ordem do catálogo (e dos campos no `list_fields`). Não renumerar.
- `**Local**: `caminho.completo`` — nome e caminho da tabela.
- `**Multi-tenant**: …` — regra de filtro por grupo. As três formas reconhecidas são "coluna direta `x`", "STRUCT embutido — filtrar direto em `x.y`" e "Exige `INNER JOIN tabela alias ON …` e filtro em `alias.coluna`". Se a linha deixar de ser reconhecida, a tabela sai da allowlist (falha fechada) e `tests/test_catalog.py` acusa.
- Tabelas markdown com `Coluna | Tipo | Alias PT-BR | Exibição` nas quatro primeiras posições. O subtítulo `###` acima define o nível/grupo das colunas.

**Cuidado:** qualquer tabela markdown no arquivo com 4+ colunas cuja primeira célula seja uma palavra vira coluna. Foi assim que a tabela de cenários de faturamento virou a coluna fantasma `Cenário` de `financial_transaction`. Tabela de enum fica com até 3 colunas; texto de apoio com tabelas maiores vai para um arquivo `_`.

## Tabela nova

1. Criar `<nome_fisico>.md` seguindo o formato acima, com o próximo número de seção.
2. Declarar os JOINs em `_relacionamentos.md`.
3. Mapear o domínio em `TABLE_TO_DOMAIN` (`schema_extractor.py`).
4. Rodar `tests/test_catalog.py` e `tests/test_tables.py`.
