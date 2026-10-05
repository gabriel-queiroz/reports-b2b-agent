"""Aponta `domain.agents.reports_b2b` para a raiz deste repositório.

No projeto principal este é o diretório real do pacote. Aqui, fora dele, os
imports de produção (`domain.agents.reports_b2b.catalog`, ...) resolvem para
os arquivos da raiz sem copiar nada.
"""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parents[4])]
