#!/usr/bin/env bash
# Atualiza o reports_b2b do projeto principal para a versão de agente único.
#
# Pré-requisito: o projeto principal já recebeu a migração anterior (catálogo
# em data/tabelas/, nomes em inglês) — a versão do commit BASE desta POC.
#
# Uso:
#   scripts/update_single_agent.sh            # simulação: só mostra o que mudaria
#   scripts/update_single_agent.sh --apply    # aplica (pede confirmação)
#
# Variáveis (opcionais): SOURCE, DEST (as mesmas do migrate_to_main.sh) e
# BASE, o commit da POC que foi levado na migração anterior.
#
# Antes de copiar, este script:
#   1. confere que o destino está na versão anterior (e não na original nem já
#      atualizado);
#   2. lista arquivos que alguém mudou no projeto principal depois da migração
#      anterior — a cópia sobrescreve esses arquivos;
#   3. procura, fora do reports_b2b, usos do que saiu nesta versão.
# A cópia em si é feita pelo migrate_to_main.sh.

set -euo pipefail

SOURCE="${SOURCE:-/Users/queiroz.gabriel/Development/pocs/react-b2b-agent}"
DEST="${DEST:-/Users/queiroz.gabriel/Development/ifp-beni-agents/packages/domain/agents/reports_b2b}"
BASE="${BASE:-fd07109}"

case "${1:-}" in
  --apply|"") ;;
  *) echo "Uso: $0 [--apply]" >&2; exit 2 ;;
esac

# O que saiu nesta versão (agente único). Uso fora do pacote quebra o import.
REMOVED_NOW='report_generator|generate_query_tool|_generate_sql_internal|build_domains_text|full_documentation|get_all_tables_for_sql_generation|sanitize_question|InvalidQuestionError|MAX_QUESTION_LENGTH'

fail() { echo "ERRO: $*" >&2; exit 1; }

[ -d "$SOURCE/.git" ] || fail "origem não é um clone git da POC: $SOURCE"
[ -d "$DEST" ] || fail "destino não existe: $DEST"
git -C "$SOURCE" cat-file -e "$BASE^{commit}" 2>/dev/null \
  || fail "commit BASE=$BASE não existe na POC. Rode 'git -C $SOURCE fetch --unshallow' ou ajuste BASE."
[ -f "$SOURCE/reports_react_agent/prompts.py" ] \
  || fail "a POC ainda não tem a versão de agente único. Rode 'git -C $SOURCE pull'."

# ------------------------------------------------------ 1. versão do destino --

echo "== Versão do projeto principal"
if [ ! -d "$DEST/data/tabelas" ]; then
  fail "o destino ainda não tem data/tabelas/: a migração anterior não foi feita. Use scripts/migrate_to_main.sh."
fi
ALREADY_UPDATED=0
if [ -f "$DEST/reports_react_agent/prompts.py" ] && [ ! -d "$DEST/report_generator" ]; then
  echo "o destino já está na versão de agente único; a cópia só traz o que mudou depois."
  ALREADY_UPDATED=1
elif [ -f "$DEST/report_generator/tools/generate_query_tool.py" ]; then
  echo "versão anterior (catálogo por tabela + gerador de SQL separado): ok para atualizar."
else
  fail "estado inesperado: não há report_generator/ nem reports_react_agent/prompts.py. Confira o destino antes de seguir."
fi
echo

# ----------------------------------- 2. mudanças locais desde a migração BASE --

echo "== Arquivos mudados no projeto principal depois da migração anterior"
CHANGED_LOCALLY=0
[ "$ALREADY_UPDATED" -eq 1 ] && echo "(pulado: o destino já foi atualizado; compare pelo git log do projeto principal)"
[ "$ALREADY_UPDATED" -eq 0 ] && while IFS= read -r path; do
  base_content="$(git -C "$SOURCE" show "$BASE:$path" 2>/dev/null)" || continue
  if [ -f "$DEST/$path" ] && [ "$base_content" != "$(cat "$DEST/$path")" ]; then
    echo "  $path"
    CHANGED_LOCALLY=$((CHANGED_LOCALLY + 1))
  fi
done < <(git -C "$SOURCE" ls-tree -r --name-only "$BASE" \
  | grep -vE '^(_local/|scripts/migrate_to_main|scripts/update_single_agent|docs/|README\.md|requirements-dev\.txt|\.gitignore)')
if [ "$ALREADY_UPDATED" -eq 1 ]; then
  :
elif [ "$CHANGED_LOCALLY" -eq 0 ]; then
  echo "nenhum"
else
  echo
  echo "ATENÇÃO: os $CHANGED_LOCALLY arquivo(s) acima foram alterados no projeto principal"
  echo "depois da migração anterior e serão SOBRESCRITOS. Veja o que mudou com:"
  echo "  git -C <ifp-beni-agents> log -p -- <arquivo>"
  echo "e reaplique à mão o que precisar ficar."
fi
echo

# ------------------------------------------------- 3. usos fora do pacote --

echo "== Usos, fora do reports_b2b, do que saiu nesta versão"
MAIN_ROOT="$(git -C "$DEST" rev-parse --show-toplevel)"
REL_DEST="$(cd "$DEST" && pwd)"
REL_DEST="${REL_DEST#"$MAIN_ROOT"/}"
EXTERNAL="$(cd "$MAIN_ROOT" && git grep -nE "$REMOVED_NOW" -- ':!'"$REL_DEST" 2>/dev/null || true)"
if [ -n "$EXTERNAL" ]; then
  echo "$EXTERNAL"
  echo
  echo "ATENÇÃO: ajuste esses pontos depois da cópia (veja docs/atualizacao-agente-unico.md)."
else
  echo "nenhum"
fi
echo

# ------------------------------------------------------------- 4. cópia --

exec env SOURCE="$SOURCE" DEST="$DEST" CALLER="$0" "$SOURCE/scripts/migrate_to_main.sh" "$@"
