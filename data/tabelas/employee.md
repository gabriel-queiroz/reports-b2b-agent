## 7. Employee (Colaboradores)

**Local**: `main.ifoodoffice_management_silver.employee`

**Descrição**: A tabela master de dados de funcionários da plataforma iFood Benefícios. Centraliza informações de identidade dos colaboradores.

**Volume de dados:** ~5,22M registros | **Última atualização:** 2026-07-22

**Domínio**: `colaboradores`

**Multi-tenant**: não possui coluna de grupo. Exige `INNER JOIN fintech_companies.companies c ON employee.company_id = c.company_id` e filtro em `c.company_group_id`.

**Partição obrigatória**: nenhuma documentada.

**Filtros padrão**: `deleted = false`, `test = false`.

**Colunas que NÃO existem** (confirmado no dump do Databricks): `employee_id`, `employee_name`. O `sql_system.txt` as listava como "campos principais" — era invenção do prompt. Os equivalentes reais são `id` e `name`.

> **Exibição vazia** = coluna que existe e é aceita pelo guard, mas **não é campo de relatório**:
> serve a JOIN, a filtro ou é ruído técnico. Em `employee` isso vale para `test` e `test_mode` — o agente pode filtrar por elas, mas não as oferece ao usuário como coluna de saída.

### Categorias de Campos

#### 🔑 Identificação do Colaborador (identidade única)
Use para identificar e referenciar colaboradores nos relatórios.

| Coluna | Tipo | Alias PT-BR | Exibição | Descrição | Uso | Valores |
|--------|------|-------------|----------|-----------|-----|--------|
| `id` | STRING | `id_colaborador` | ID Colaborador | UUID único do funcionário. Chave primária da tabela. | ✅ Essencial | — |
| `person_id` | STRING | `id_usuario_iFB` |  | Person ID iFB — identificador usado para **filtrar** um colaborador específico. | ✅ Filtro | — |

#### 👤 Dados Pessoais
Dados pessoais armazenados em claro (sem sufixo `_hash`). O CSV de relatório conterá os valores originais.

> **Decisão registrada:** `name`, `email`, `cpf` e `phone_number` continuam sendo
> oferecidos como **campos de saída** ("Nome", "Email", "CPF", "Telefone"). Para
> **identificar/filtrar** um colaborador, use **somente** `person_id`; `name`,
> `email` e `cpf` **não são filtráveis** no domínio `colaboradores` (a conversão
> CPF→personId acontece antes de chegar aqui). Quem pedir esses campos como saída
> recebe um CSV com os dados em claro, seguindo o tratamento de LGPD do relatório.

| Coluna | Tipo | Alias PT-BR | Exibição | Descrição | Uso | Valores |
|--------|------|-------------|----------|-----------|-----|--------|
| `name` | STRING | `nome_colaborador` | Nome | Nome completo do colaborador. | Relatórios (não filtrar) | — |
| `email` | STRING | `email_colaborador` | Email | Email corporativo do colaborador. | Relatórios (não filtrar) | — |
| `cpf` | STRING | `cpf_colaborador` | CPF | CPF do colaborador (em claro). | Relatórios (não filtrar) | — |
| `phone_number` | STRING | `telefone_colaborador` | Telefone | Telefone do colaborador. | Relatórios | — |
| `born_date` | STRING | `data_nascimento_colaborador` | Data Nascimento | Data de nascimento em ISO format (YYYY-MM-DD). Pode ser nula. | Opcional | — |

#### 🏢 Empresa
Vínculo do colaborador com a empresa.

| Coluna | Tipo | Alias PT-BR | Exibição | Descrição | Uso | Valores |
|--------|------|-------------|----------|-----------|-----|--------|
| `company_id` | STRING | `id_empresa_colaborador` | ID Empresa | UUID da empresa/subsidiária onde o colaborador trabalha. **Obrigatório para filtros multi-tenant.** | ✅ Essencial | — |

#### 🔍 Metadata e Auditoria
Campos de controle, datas e flags técnicas.

| Coluna | Tipo | Alias PT-BR | Exibição | Descrição | Uso | Valores |
|--------|------|-------------|----------|-----------|-----|--------|
| `deleted` | BOOLEAN | `deletado_colaborador` | Inativo | Flag de soft delete. `true` = colaborador inativo/desligado. Filtrar `deleted = false` para ativos; `deleted = true` para inativos. | ✅ Filtro | — |
| `test` | BOOLEAN | `teste_colaborador` |  | Flag indicando dados de teste. `true` = registro de teste, `false` = produção. Filtrar conforme necessário — **filtro apenas, não é campo de relatório**. | Teste | — |
| `test_mode` | STRING | `modo_teste` |  | Modo de teste técnico (valor informacional). Ignorar em relatórios de produção — **não é campo de relatório**. | Ignorar | loadtest |
| `created_at` | STRING | `data_criacao_colaborador` | Data de Criação | Timestamp ISO 8601 de quando o colaborador foi criado no sistema. | Auditoria | — |
