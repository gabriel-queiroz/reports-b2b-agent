# Prompt: levar o reports_b2b da POC para o projeto principal

Cole o texto abaixo no Claude Code, na sua máquina. Ele usa o `scripts/migrate_to_main.sh` deste repositório.

```
Quero levar a versão refatorada do agente reports_b2b da POC para o projeto principal.

- POC (origem): /Users/queiroz.gabriel/Development/pocs/react-b2b-agent
- Projeto principal (destino): /Users/queiroz.gabriel/Development/ifp-beni-agents/packages/domain/agents/reports_b2b

Passos:

1. Na POC, rode `git pull` para ficar com a última versão.
2. No ifp-beni-agents, confira se `git status` está limpo no reports_b2b e crie um branch novo a partir da main atualizada (ex.: `refactor/reports-b2b-catalogo-por-tabela`). Se houver mudanças pendentes, pare e me pergunte.
3. Da pasta da POC, rode `scripts/migrate_to_main.sh` sem argumentos (só simula). Me mostre o resumo: quantos arquivos criados, atualizados e apagados, e os "usos externos de nomes que mudaram". O único arquivo apagado esperado é data/schema.md. Se aparecer outro, pare e me pergunte.
4. Se estiver tudo como esperado, rode `echo s | scripts/migrate_to_main.sh --apply`.
5. Se o passo 3 tiver apontado código fora do reports_b2b usando nomes antigos, atualize para os novos:
   - build_campos_solicitados_block → build_requested_fields_block
   - is_detalhe_column → is_detail_column
   - leitura de data/schema.md → funções do catalog.py / schema_extractor.py (data/tabelas/)
6. Rode os testes do pacote no ambiente do projeto principal (`pytest packages/domain/agents/reports_b2b/tests`) e depois a suíte que o projeto usa normalmente. Se algo falhar, investigue e me explique antes de mudar código do reports_b2b.
7. Faça commit no branch novo com uma mensagem descritiva. NÃO faça push nem abra PR sem eu pedir.

Não copie a pasta _local/ (são stubs só para rodar os testes fora do projeto) e não mexa no conteúdo de data/tabelas/. No fim, me diga o que mudou, o resultado dos testes e o que ficou pendente.
```
