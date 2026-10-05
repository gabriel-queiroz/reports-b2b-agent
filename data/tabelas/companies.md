## 3. Companies (Empresas)

**Local**: `fintech_companies.companies`

**Descrição**: Master de dados cadastrais das empresas. Centraliza informações de identificação, endereços comerciais, geolocalização, grupo corporativo.

**Volume**: Centenas de milhares | **Última atualização**: 2026-07-22

**Domínio**: transversal — usada por todos os domínios como ponte para o filtro multi-tenant.

**Multi-tenant**: coluna direta `company_group_id`.

**Alias obrigatório**: quando entrar por JOIN, usar o alias `c` (exigido pelo prompt e pelo `sql_guard.py`).

**Filtros padrão**: `deleted = false`. A coluna `test` **existe** na tabela física, mas por decisão do time (2026-08-13) não é documentada nem usada como filtro padrão — relatórios não separam empresa de teste.

### Colunas

| Coluna | Tipo | Alias PT-BR | Exibição | Descrição | Valores |
|--------|------|-------------|----------|-----------|--------|
| `company_id` | STRING | `id_empresa` | ID Empresa | UUID único. Chave de JOIN — não é campo de relatório | — |
| `cnpj` | STRING | `cnpj_empresa` | CNPJ Empresa | CNPJ (14 dígitos) | — |
| `social_name` | STRING | `razao_social_empresa` | Razão Social | Razão social | — |
| `company_group_id` | STRING | `company_group_id` | ID Grupo | UUID do grupo corporativo. Filtro multi-tenant e coluna de saída obrigatória — não é campo de relatório | — |
| `company_group_name` | STRING | `nome_grupo_empresa` | Nome Grupo | Nome da licença (grupo corporativo) | — |
| `deleted` | BOOLEAN | `deletado_empresa` |  | Soft delete. Usado no filtro padrão — não é campo de relatório | — |
