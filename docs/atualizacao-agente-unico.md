# Atualização: agente único (o ReAct escreve o SQL)

Para o `ifp-beni-agents` que já recebeu a migração anterior no branch `refactor/reports-b2b-table-catalog`: catálogo em `data/tabelas/` e nomes em inglês, que é a versão do commit `fd07109` desta POC. Este guia leva o `reports_b2b` desse branch para a versão em que o próprio agente ReAct escreve o SQL. A atualização entra como um commit novo no mesmo branch.

Se o projeto principal ainda está na versão original (com `data/schema.md`), use `scripts/migrate_to_main.sh` e o `scripts/migrate_to_main.prompt.md`. Esse caminho já leva direto para esta versão.

## O que muda

| | Antes | Depois |
|---|---|---|
| Quem escreve o SQL | Um segundo LLM (GPT-4.1) dentro da `execute_query` | O próprio agente ReAct (Gemini) |
| Prompts | `agente.txt` + `sql_system.txt` + `sql_user.txt` | Um só: `reports_react_agent/agent_prompt.txt` |
| Catálogo no contexto | Inteiro no gerador (~43k caracteres) | Índice no prompt (~24k no total); schema de cada tabela pela tool `get_table_schema` |
| Tools do agente | `list_fields`, `execute_query(question, domain, desired_fields)` | `list_fields`, `resolve_fields`, `get_table_schema`, `execute_query(sql)` |
| SQL recusado pelo `sql_guard` | Retry escondido no gerador, até 2 vezes | Volta como `"status": "invalid_sql"` com o motivo; o agente corrige na conversa |

Continua igual: o `sql_guard`, o filtro de tenant vindo só da sessão, o SQL enviado ao Reports Service ser o regerado a partir da AST, o `catalog.py` e o `data/tabelas/`.

## Arquivos

**Saem**
- `report_generator/` inteiro (`generate_query_tool.py`, `prompts/__init__.py`, `sql_system.txt`, `sql_user.txt`)
- `tests/test_sql_retry.py`, `tests/test_edge_guardrails.py`, `tests/test_prompts.py`

**Entram**
- `reports_react_agent/agent_prompt.txt`: o prompt único, sucessor do `agente.txt`
- `reports_react_agent/few_shot.txt`: os mesmos exemplos, agora com `<GROUP_ID>` no lugar do UUID fictício
- `reports_react_agent/prompts.py`: monta o prompt (`agent_system_prompt(group_id)`)
- `tools/resolve_fields.py`
- `tests/test_execute_query.py`, `tests/test_agent_prompt.py`

**Mudam**
- `reports_react_agent/agent.py`, `tools/execute_query.py`, `tools/__init__.py`, `guardrails.py`, `schema_extractor.py`, `data/tabelas/employee.md` (uma frase) e alguns testes

**Nomes removidos.** Se algo fora do `reports_b2b` usar um destes, o import quebra:

| Removido | O que usar |
|---|---|
| `report_generator.prompts.agent_system_prompt(domains, group_id)` | `reports_react_agent.prompts.agent_system_prompt(group_id)` |
| `report_generator.tools.generate_query_tool`, `_generate_sql_internal` | Nada. O SQL vem do agente; quem valida e executa é `tools.execute_query` |
| `schema_extractor.build_domains_text` | `schema_extractor.build_tables_index` |
| `schema_extractor.full_documentation`, `get_all_tables_for_sql_generation` | `schema_extractor.table_doc(tabela)` |
| `guardrails.sanitize_question`, `InvalidQuestionError`, `MAX_QUESTION_LENGTH` | Nada. Nenhum texto do usuário é mais interpolado em prompt |

## Passo a passo

1. Na POC, atualize: `git pull`. O script precisa do histórico até o `fd07109`. Se o clone for raso, rode `git fetch --unshallow`.
2. No `ifp-beni-agents`, vá para o branch da migração anterior e atualize. O `reports_b2b` precisa estar sem mudanças pendentes:
   ```bash
   git switch refactor/reports-b2b-table-catalog
   git pull
   ```
3. Simule, a partir da POC:
   ```bash
   scripts/update_single_agent.sh
   ```
   O script para se o `ifp-beni-agents` não estiver no `refactor/reports-b2b-table-catalog` ou se estiver atrás do remoto (pelo último fetch). Depois confere se o destino está na versão anterior e lista três coisas:
   - arquivos do `reports_b2b` que alguém mudou no projeto principal depois da migração anterior. Esses arquivos **serão sobrescritos**, então reaplique à mão o que precisar ficar;
   - usos, fora do pacote, dos nomes removidos;
   - o que será criado, atualizado e apagado.
4. Aplique:
   ```bash
   scripts/update_single_agent.sh --apply
   ```
5. Ajuste os usos externos apontados no passo 3 (tabela acima), rode `pytest packages/domain/agents/reports_b2b/tests` e depois a suíte normal do projeto.
6. Faça o commit no `refactor/reports-b2b-table-catalog`. Se o branch já tem um PR aberto, o commit entra nele no próximo push.

Os caminhos padrão podem ser trocados com `SOURCE=... DEST=...`, o commit da migração anterior com `BASE=...` e o branch esperado com `TARGET_BRANCH=...` (vazio desliga a checagem).

## Prompt para o Claude Code

Cole na sua máquina:

```
Quero atualizar o reports_b2b do ifp-beni-agents para a versão de agente único da POC: o próprio agente ReAct passa a escrever o SQL, o gerador separado (report_generator/, GPT-4.1) sai e os três prompts viram um só. A migração anterior (data/tabelas/, nomes em inglês) está no branch refactor/reports-b2b-table-catalog, e esta atualização entra como um commit novo nesse mesmo branch.

- POC (origem): /Users/queiroz.gabriel/Development/pocs/react-b2b-agent
- Projeto principal (destino): /Users/queiroz.gabriel/Development/ifp-beni-agents/packages/domain/agents/reports_b2b
- Guia completo: docs/atualizacao-agente-unico.md na POC. Leia antes de começar.

Passos:

1. Na POC, rode `git pull`. Se o clone for raso, rode `git fetch --unshallow`.
2. No ifp-beni-agents, rode `git switch refactor/reports-b2b-table-catalog` e `git pull`. Não crie branch novo. Se houver mudanças pendentes no reports_b2b, ou se o pull trouxer conflito, pare e me pergunte.
3. Da pasta da POC, rode `scripts/update_single_agent.sh` (só simula). Se ele parar por causa do branch, resolva conforme a mensagem e rode de novo. Me mostre:
   - o branch e a versão detectada do destino;
   - os arquivos mudados no projeto principal depois da migração anterior. Para cada um, me mostre o diff (git log -p) e diga se a mudança precisa ser reaplicada depois da cópia;
   - os usos externos de nomes removidos;
   - quantos arquivos serão criados, atualizados e apagados. Os apagados esperados são report_generator/ inteiro e tests/test_sql_retry.py, test_edge_guardrails.py e test_prompts.py. Se aparecer outro, pare e me pergunte.
4. Espere eu confirmar. Depois rode `echo s | scripts/update_single_agent.sh --apply`.
5. Reaplique as mudanças locais que eu aprovar no passo 3 e ajuste os usos externos conforme a tabela "Nomes removidos" do guia.
6. Rode `pytest packages/domain/agents/reports_b2b/tests` e depois a suíte normal do projeto. Se algo falhar, investigue e me explique antes de mudar código do reports_b2b.
7. Confira no BaseAgent do projeto principal se o limite de iterações do loop ReAct cabe o fluxo novo: list_fields, resolve_fields, um get_table_schema por tabela e até 3 tentativas de execute_query. Se não couber, me avise em vez de mudar.
8. Faça commit no refactor/reports-b2b-table-catalog com uma mensagem descritiva. NÃO faça push nem abra PR sem eu pedir.

Não copie _local/ e não mexa no conteúdo de data/tabelas/. No fim, me diga o que mudou, o resultado dos testes e o que ficou pendente.
```

## Antes de ir para produção

- **Qualidade do SQL com o Gemini.** Antes o SQL vinha do GPT-4.1. Rode as perguntas reais, incluindo as 6 do `few_shot.txt`, nas duas versões e compare o SQL que chega ao Reports Service. O log `execute_query: SQL accepted` traz o SQL de cada pedido.
- **Taxa de `invalid_sql`.** Acompanhe o log `execute_query: SQL rejected by guard`. Recusa frequente do mesmo tipo pede ajuste no prompt ou nos exemplos.
- **Limite de iterações do `BaseAgent`.** Um relatório agora leva de 4 a 8 chamadas de tool.
- **Tamanho da resposta do modelo.** O gerador antigo usava `max_tokens=4096` para não truncar SQL longo. O agente usa o padrão do `genplat_provider`. Se aparecer SQL cortado, defina `max_tokens` em `_create_llm` do `agent.py`.

## Como desfazer

Antes do commit:

```bash
git restore --source=HEAD --staged --worktree -- packages/domain/agents/reports_b2b
git clean -fd -- packages/domain/agents/reports_b2b
```

Depois do commit (antes do push): `git reset --hard HEAD~1` no `refactor/reports-b2b-table-catalog`. Depois do push: `git revert` do commit, para não reescrever o histórico de um branch compartilhado.
