#!/usr/bin/env bash
# Copia este repositório para o pacote reports_b2b do projeto principal.
#
# Uso:
#   scripts/migrate_to_main.sh            # simulação: só mostra o que mudaria
#   scripts/migrate_to_main.sh --apply    # copia de verdade (pede confirmação)
#
# Caminhos padrão (sobrescreva com SOURCE=... DEST=... se mudarem):
#   SOURCE  este repositório (a POC)
#   DEST    packages/domain/agents/reports_b2b do projeto principal
#
# Ficam de fora: _local/ (stubs só para rodar os testes fora do projeto),
# .git, .gitignore, README.md, requirements-dev.txt e caches. Arquivos do
# destino que não existem mais aqui (ex.: data/schema.md) são apagados.

set -euo pipefail

SOURCE="${SOURCE:-/Users/queiroz.gabriel/Development/pocs/react-b2b-agent}"
DEST="${DEST:-/Users/queiroz.gabriel/Development/ifp-beni-agents/packages/domain/agents/reports_b2b}"

APPLY=0
case "${1:-}" in
  --apply) APPLY=1 ;;
  "") ;;
  *) echo "Uso: $0 [--apply]" >&2; exit 2 ;;
esac

# Nomes públicos que mudaram ou saíram. Se algo fora do reports_b2b usar
# algum deles, a cópia quebra o projeto principal.
REMOVED_NAMES='build_campos_solicitados_block|is_detalhe_column|schema_path|schema\.md|tabelas_dir'

EXCLUDES=(
  --exclude=_local/
  --exclude=.git/
  --exclude=.gitignore
  --exclude=README.md
  --exclude=requirements-dev.txt
  --exclude=scripts/migrate_to_main.sh
  --exclude=__pycache__/
  --exclude=.pytest_cache/
  --exclude=.venv/
  --exclude=.DS_Store
)

fail() { echo "ERRO: $*" >&2; exit 1; }

command -v rsync >/dev/null || fail "rsync não encontrado"
command -v git >/dev/null || fail "git não encontrado"

# ---------------------------------------------------------------- checagens --

[ -d "$SOURCE" ] || fail "origem não existe: $SOURCE"
[ -d "$DEST" ] || fail "destino não existe: $DEST"
[ -f "$SOURCE/catalog.py" ] && [ -d "$SOURCE/data/tabelas" ] \
  || fail "origem não parece ser a POC (falta catalog.py ou data/tabelas): $SOURCE"
[ -f "$DEST/graph.py" ] && [ -f "$DEST/__init__.py" ] \
  || fail "destino não parece ser o pacote reports_b2b (falta graph.py): $DEST"

SOURCE="$(cd "$SOURCE" && pwd)"
DEST="$(cd "$DEST" && pwd)"
[ "$SOURCE" != "$DEST" ] || fail "origem e destino são a mesma pasta"

MAIN_ROOT="$(git -C "$DEST" rev-parse --show-toplevel 2>/dev/null)" \
  || fail "o destino não está num repositório git; sem git não há como desfazer"

if [ -n "$(git -C "$SOURCE" status --porcelain 2>/dev/null)" ]; then
  echo "AVISO: a POC tem mudanças não commitadas; elas também serão copiadas."
fi

DIRTY="$(git -C "$MAIN_ROOT" status --porcelain -- "$DEST")"
if [ -n "$DIRTY" ]; then
  echo "$DIRTY"
  fail "o reports_b2b do projeto principal tem mudanças não commitadas. Commite ou faça stash antes."
fi

echo "Origem : $SOURCE"
echo "Destino: $DEST"
echo "Branch : $(git -C "$MAIN_ROOT" branch --show-current)"
echo

# ------------------------------------------------ referências fora do pacote --

echo "== Usos externos de nomes que mudaram"
REL_DEST="${DEST#"$MAIN_ROOT"/}"
EXTERNAL="$(cd "$MAIN_ROOT" && git grep -nE "$REMOVED_NAMES" -- ':!'"$REL_DEST" 2>/dev/null || true)"
if [ -n "$EXTERNAL" ]; then
  echo "$EXTERNAL"
  echo
  echo "ATENÇÃO: o código acima, fora do reports_b2b, usa nomes que mudaram."
  echo "Ajuste esses pontos depois da cópia (novos nomes: build_requested_fields_block,"
  echo "is_detail_column, tables_dir; o schema.md virou data/tabelas/)."
else
  echo "nenhum"
fi
echo

# ------------------------------------------------------------------- cópia --

echo "== O que muda no destino"
# -v em vez de --itemize-changes: funciona no rsync antigo do macOS e no openrsync.
CHANGES="$(rsync -a -c -v --delete --dry-run "${EXCLUDES[@]}" "$SOURCE/" "$DEST/" \
  | grep -vE '^(building file list|sending incremental|sent |total size|Transfer starting|$)' \
  | grep -vE '/$' || true)"
if [ -z "$CHANGES" ]; then
  echo "nada: o destino já está igual à POC."
  exit 0
fi
echo "$CHANGES"
echo
DELETIONS="$(printf '%s\n' "$CHANGES" | grep -c '^deleting ' || true)"
echo "($DELETIONS arquivo(s) serão apagados; os demais são criados ou atualizados)"
echo

if [ "$APPLY" -eq 0 ]; then
  echo "Simulação apenas. Para aplicar: $0 --apply"
  exit 0
fi

printf "Aplicar essas mudanças em %s? [s/N] " "$DEST"
read -r ANSWER
case "$ANSWER" in
  s|S|sim|y|Y) ;;
  *) echo "Cancelado."; exit 1 ;;
esac

rsync -a -c --delete "${EXCLUDES[@]}" "$SOURCE/" "$DEST/"

echo
echo "Copiado. Próximos passos no projeto principal ($MAIN_ROOT):"
echo "  git status -- $REL_DEST"
echo "  pytest $REL_DEST/tests"
echo "Para desfazer: git -C $MAIN_ROOT restore --source=HEAD --staged --worktree -- $REL_DEST && git -C $MAIN_ROOT clean -fd -- $REL_DEST"
