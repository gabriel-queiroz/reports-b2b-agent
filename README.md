# reports_b2b

Agente ReAct de relatórios B2B do iFood Benefícios: pergunta em linguagem natural → SQL validado pelo `sql_guard` → relatório .csv gerado pelo Reports Service.

Nesta versão o catálogo das tabelas do Databricks está dividido em um arquivo por tabela, em `data/tabelas/`, no lugar do antigo `data/schema.md`. O formato e as regras de cada arquivo estão em [`data/tabelas/_LEIAME.md`](data/tabelas/_LEIAME.md).

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

`scripts/migrate_to_main.sh` copia este repositório para `packages/domain/agents/reports_b2b` do `ifp-beni-agents`, deixando de fora `_local/`, `.git`, `README.md` e `requirements-dev.txt`, e apaga o `data/schema.md` antigo. Sem argumentos só simula; com `--apply` copia depois de pedir confirmação. Recusa rodar se o destino tiver mudanças não commitadas e avisa se algum código fora do pacote usa nomes que mudaram.

```bash
scripts/migrate_to_main.sh            # simulação
scripts/migrate_to_main.sh --apply    # copia
```

Os caminhos padrão podem ser trocados com `SOURCE=... DEST=...`.
