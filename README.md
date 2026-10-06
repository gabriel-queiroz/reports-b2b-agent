# reports_b2b

Agente ReAct de relatórios B2B do iFood Benefícios: pergunta em linguagem natural → SQL escrito pelo próprio agente e validado pelo `sql_guard` → relatório .csv gerado pelo Reports Service.

## Como funciona

Um agente só, com um prompt só (`reports_react_agent/agent_prompt.txt`). Ele conversa com o usuário, confirma o relatório e escreve o SQL. Não existe mais um segundo LLM gerando a query.

O prompt leva o índice do catálogo (tabelas, domínios e relacionamentos), as regras gerais e os exemplos pergunta → SQL (`few_shot.txt`, com o `group_id` da sessão). O schema de cada tabela vem por tool, quando o agente precisa.

| Tool | Para quê |
|------|----------|
| `list_fields(domain)` | Campos do domínio com o nome que o usuário vê |
| `resolve_fields(domain, desired_fields)` | Campos confirmados → coluna física + alias PT-BR, e quando a medida entra com `SUM` |
| `get_table_schema(table)` | Colunas, aliases, regra multi-tenant, partição, filtros padrão e enums de uma tabela |
| `execute_query(sql)` | Valida no `sql_guard` e pede o relatório |

Quando o `sql_guard` recusa, a `execute_query` devolve `"status": "invalid_sql"` com o motivo, e o agente corrige na mesma conversa. O `group_id` e o usuário vêm do state da sessão, nunca do modelo; o que vai para o Reports Service é o SQL regerado a partir da AST, com o filtro de tenant garantido.

O catálogo das tabelas do Databricks está dividido em um arquivo por tabela, em `data/tabelas/`. O formato e as regras de cada arquivo estão em [`data/tabelas/_LEIAME.md`](data/tabelas/_LEIAME.md).

## Testes

```bash
pip install -r requirements-dev.txt
pytest tests
```

No projeto principal os imports `domain.agents.reports_b2b...` resolvem pelo pacote real. Fora dele, o `tests/conftest.py` usa os stubs mínimos de `_local/`, que não fazem parte do código de produção.

## Migração

`scripts/split_schema.py` refaz a divisão a partir de um `schema.md` (migração única), caso o arquivo tenha mudado no projeto principal:

```bash
python scripts/split_schema.py caminho/para/schema.md data/tabelas
```

## Levar para o projeto principal

`scripts/migrate_to_main.sh` copia este repositório para `packages/domain/agents/reports_b2b` do `ifp-beni-agents`, deixando de fora `_local/`, `.git`, `README.md` e `requirements-dev.txt`, e apaga o que não existe mais aqui (o `data/schema.md` e o `report_generator/` antigos). Sem argumentos só simula; com `--apply` copia depois de pedir confirmação. Recusa rodar se o destino tiver mudanças não commitadas e avisa se algum código fora do pacote usa nomes que mudaram.

```bash
scripts/migrate_to_main.sh            # simulação
scripts/migrate_to_main.sh --apply    # copia
```

Os caminhos padrão podem ser trocados com `SOURCE=... DEST=...`. Para o Claude Code fazer a migração inteira (branch, cópia, ajustes e testes), use o prompt em `scripts/migrate_to_main.prompt.md`.
