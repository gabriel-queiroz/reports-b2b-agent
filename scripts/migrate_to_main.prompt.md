# Prompt: levar o reports_b2b da POC para o projeto principal

Cole o texto abaixo no Claude Code, na sua máquina. Ele usa o `scripts/migrate_to_main.sh` deste repositório.

```
Quero levar a versão refatorada do agente reports_b2b da POC para o projeto principal. Nela, o próprio agente ReAct escreve o SQL (o gerador separado com GPT-4.1, em report_generator/, saiu), o prompt é um só e o catálogo está em data/tabelas/, um arquivo por tabela.

- POC (origem): /Users/queiroz.gabriel/Development/pocs/react-b2b-agent
- Projeto principal (destino): /Users/queiroz.gabriel/Development/ifp-beni-agents/packages/domain/agents/reports_b2b

Passos:

1. Na POC, rode `git pull` para ficar com a última versão.
2. No ifp-beni-agents, confira se `git status` está limpo no reports_b2b e crie um branch novo a partir da main atualizada (ex.: `refactor/reports-b2b-catalogo-por-tabela`). Se houver mudanças pendentes, pare e me pergunte.
3. Da pasta da POC, rode `scripts/migrate_to_main.sh` sem argumentos (só simula). Me mostre o resumo: quantos arquivos criados, atualizados e apagados, e os "usos externos de nomes que mudaram". Os apagados esperados são data/schema.md, tudo em report_generator/ e os testes do gerador antigo (test_sql_retry.py, test_edge_guardrails.py, test_prompts.py). Se aparecer outro, pare e me pergunte.
4. Se estiver tudo como esperado, rode `echo s | scripts/migrate_to_main.sh --apply`.
5. Se o passo 3 tiver apontado código fora do reports_b2b usando nomes antigos, atualize para os novos:
   - build_campos_solicitados_block → build_requested_fields_block
   - is_detalhe_column → is_detail_column
   - leitura de data/schema.md → funções do catalog.py / schema_extractor.py (data/tabelas/)
   - report_generator.prompts.agent_system_prompt → reports_react_agent.prompts.agent_system_prompt (agora só recebe group_id)
   - report_generator.tools.generate_query_tool / _generate_sql_internal → não existem mais; o SQL vem do agente e passa pela tools/execute_query.py (que agora recebe só `sql`)
   - sanitize_question / InvalidQuestionError / MAX_QUESTION_LENGTH → removidos (nenhum texto do usuário é mais interpolado em prompt)
6. Rode os testes do pacote no ambiente do projeto principal (`pytest packages/domain/agents/reports_b2b/tests`) e depois a suíte que o projeto usa normalmente. Se algo falhar, investigue e me explique antes de mudar código do reports_b2b.
7. O modelo do agente (Gemini, em reports_react_agent/agent.py) agora também escreve o SQL. Confira se o BaseAgent do projeto principal tem limite de iterações suficiente para: list_fields, resolve_fields, um get_table_schema por tabela, e até 3 tentativas de execute_query. Se o limite for menor, me avise em vez de mudar.
8. Faça commit no branch novo com uma mensagem descritiva. NÃO faça push nem abra PR sem eu pedir.

Não copie a pasta _local/ (são stubs só para rodar os testes fora do projeto) e não mexa no conteúdo de data/tabelas/. No fim, me diga o que mudou, o resultado dos testes e o que ficou pendente.
```
