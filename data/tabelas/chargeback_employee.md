## 8. Chargeback Employee (Estorno por Colaborador)

**Local**: `main.ifoodoffice_recharge_chargeback.chargeback_employee`

**Descrição**: Detalhe do estorno no nível do colaborador. Uma linha por colaborador dentro de um estorno.

**Domínio**: `estorno_recarga` — estorno de recarga.

**Multi-tenant**: Exige `INNER JOIN chargeback ch ON chargeback_employee.chargeback_id = ch.id` e filtro em `ch.group_id`.

**Partição obrigatória**: `dt` (DATE) — data de partição.

**Filtros padrão**: nenhum documentado — não foram identificadas colunas `deleted`/`test`.

**Privacidade**: `employee_name` e `tax_id` (CPF) são dados pessoais em claro — mesma situação de `employee`. Quem pedir esses campos recebe um CSV com os valores legíveis, seguindo o tratamento de LGPD do relatório.

### Estorno por Colaborador (granularidade de colaborador)

| Coluna | Tipo | Alias PT-BR | Exibição | Descrição |
|--------|------|-------------|----------|-----------|
| `id` | STRING | `id_estorno_colaborador` | ID Estorno (Colaborador) | UUID único do registro |
| `chargeback_id` | STRING | `id_estorno` | ID Estorno (Empresa) | Referência ao chargeback pai |
| `employee_id` | STRING | `id_colaborador` | ID Colaborador | ID único do funcionário |
| `employee_name` | STRING | `nome_colaborador` | Nome Colaborador | Nome do funcionário (ver nota de privacidade) |
| `person_id` | STRING | `id_usuario_iFB` | ID Usuário iFB | Person ID iFB |
| `tax_id` | STRING | `cpf_colaborador` | CPF Colaborador | CPF do colaborador (ver nota de privacidade) |
| `chargeback_employee_status` | STRING | `status_estorno_colaborador` | Status Estorno (Colaborador) | Status individual do funcionário |
| `total_requested_value` | DOUBLE | `valor_total_solicitado` | Valor Solicitado | Valor solicitado para este funcionário |
| `total_recharged_value` | DOUBLE | `valor_total_estornado` | Valor Estornado | Valor realmente estornado |
| `updated_at` | STRING | `data_estorno` | Data Estorno | Timestamp de última atualização |
| `reason` | STRING | `motivo_estorno` | Motivo Estorno | Motivo do chargeback/erro |
| `provider` | STRING | `saldo_ifood` | Benefício iFood | Saldo iFood |

> **Decisão registrada:** para **identificar/filtrar** um colaborador específico no
> estorno, use **somente** `person_id` (`id_usuario_iFB`). `employee_id` é a chave
> de JOIN com `employee.id` — **não** use `employee_id` para filtrar por CPF/personId
> (a conversão CPF→personId acontece antes de chegar aqui).

### Valores possíveis (enums)

#### Estorno de recarga — Motivo (`ChargebackReasonEnum`)

**Contexto:** motivo do estorno (coluna `reason` em `chargeback_employee`, quando aplicável).

| Valor armazenado em `reason` (pt-BR) | Significado |
|------|----------|
| `Solicitação indevida` | Solicitação indevida |
| `Valor da Solicitação indevido` | Valor da solicitação indevida |
| `Rescisão do contrato de trabalho do Beneficiado junto à Empresa` | Rescisão do contrato de trabalho |

#### Estorno de recarga — Status por item (`ChargebackItemStatusEnum`)

**Contexto:** status individual de cada colaborador no estorno (coluna `chargeback_employee_status` em `chargeback_employee`).

| Enum | Tradução |
|------|----------|
| `CONCLUDED` | Concluído |
| `ERROR` | Falha no estorno |
