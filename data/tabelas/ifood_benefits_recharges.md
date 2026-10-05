## 4. iFood Benefits Recharges (Recargas)

**Local**: `main.fintech_finance.ifood_benefits_recharges`

**Descrição**: Recargas de benefícios do iFood Benefícios. Esta tabela é a **mesclagem do pedido de recarga com os itens desse pedido** — pedido e item convivem na mesma linha.

**Volume**: ~93M registros | **Última atualização**: 2026-07-22

**Domínio**: `recargas`

**Multi-tenant**: STRUCT embutido — filtrar direto em `company_group.id`. JOIN com `companies` é opcional.

**Partição obrigatória**: `update_date` (YYYY-MM-DD, diária) e `update_month` (YYYY-MM, mensal). Use o filtro temporal adequado ao recorte pedido — `update_date` para dia/data específica, `update_month` para mês.

**Filtros padrão**: nenhum — esta tabela **não tem** `deleted` nem `test` (confirmado). Filtrar `r.deleted = false` aqui quebra a query.

**Granularidade — dois níveis na mesma linha**: uma linha = **um item da recarga** (`order_item_id`).
Uma recarga (`order_id`) ocupa tantas linhas quantos forem seus itens. Escolha o nível pela
pergunta:

| A pergunta é sobre… | Use |
|---|---|
| **a recarga** (o pedido): quantas recargas, quando foram pedidas, como foram pagas, situação do pedido | `order_id`, `order_status` e os campos de **`order_info.*`** |
| **o item da recarga** (o detalhe): valor, cashback, produto, colaborador que recebeu, situação do item | `order_item_id`, `order_item_status`, `amount`, `cashback_amount`, `product_key`, `employee_id` e os campos de **`order_item_info.*`** |

⚠️ Campo do nível da recarga **se repete** em todas as linhas do mesmo `order_id`. Por isso, ao
contar ou agrupar recargas, use `COUNT(DISTINCT r.order_id)` — `COUNT(*)` conta itens, não
recargas, e infla o número. Para contar itens, `COUNT(*)` está correto.

⚠️ Ao **listar recargas** (selecionar apenas campos do nível da recarga), use `SELECT DISTINCT`
sobre os campos de recarga — sem `DISTINCT`, a mesma recarga aparece N vezes (uma por item).
Ex.: `SELECT DISTINCT r.order_id, r.order_status, r.order_info.payment_method ...`.
⚠️ Para listar recargas com **total por recarga** (valor/cashback), use `SUM(...)` + `GROUP BY r.order_id`
— o `GROUP BY` já devolve uma linha por recarga (faz a deduplicação), então NÃO use `DISTINCT`.
Nunca misture `DISTINCT` com `SUM`.

⚠️ `amount` e `cashback_amount` são campos do **item da recarga**. Ao responder em nível de **recarga**, agregue por recarga:
- `SUM(r.amount) AS valor_recarga`
- `SUM(r.cashback_amount) AS valor_cashback` (se solicitado)
- Com `GROUP BY r.order_id` + demais campos da recarga selecionados

Selecionar `r.amount` direto junto de `r.order_id` sem agregação retorna um valor **por item**, não o total da recarga.

### Recarga (granularidade de empresa)

Campos no nível da **recarga** (`order_id`). Repetem-se em todas as linhas da mesma recarga.

#### Campos da Recarga

| Coluna | Tipo | Alias PT-BR | Exibição | Descrição | Valores |
|--------|------|-------------|----------|-----------|--------|
| `order_id` | STRING | `id_recarga` | ID Recarga | ID do pedido/transação | — |
| `order_status` | STRING | `status_recarga` | Status da Recarga | Status no nível do pedido | DISTRIBUTION_COMPLETE, CANCELED, CREATED, UNPAID_CANCELED, BOOK_PENDING_PAYMENT, SCHEDULED, BOOKED, ANTICIPATING, DISTRIBUTION_INCOMPLETE, BOOKING, BOOK_REJECTED, CANCELLING, BOOK_FAILED, UNPAID_CANCELLING, DISTRIBUTION_FAILED |
| `schedule_date` | STRING | `data_agendada_recarga` | Data Agendada (Distribuição) | Data agendada (YYYY-MM-DD) | — |
| `company_group` | STRUCT | `struct_grupo_empresa` | Dados Grupo (Empresa) | {id, name, cnpj} - Dados do grupo corporativo. **Usar para filtrar por group_id diretamente!** | — |

#### Campos da Recarga — STRUCT company_group

| Coluna | Tipo | Alias PT-BR | Exibição | Descrição | Valores |
|--------|------|-------------|----------|-----------|--------|
| `company_group.id` | STRING | `id_grupo_recarga` | ID Grupo | UUID do grupo corporativo. **Usar no filtro multi-tenant.** | — |
| `company_group.name` | STRING | `nome_grupo_empresa_recarga` | Nome do Grupo | Nome do grupo corporativo | — |
| `company_group.cnpj` | STRING | `cnpj_grupo` | CNPJ do Grupo | CNPJ do grupo corporativo | — |

#### Campos da Recarga — STRUCT order_info

| Coluna | Tipo | Alias PT-BR | Exibição | Descrição | Valores |
|--------|------|-------------|----------|-----------|--------|
| `order_info.order_id` | STRING | `id_recarga_info` | ID Recarga | ID do pedido dentro do struct. Espelha `order_id` do topo | — |
| `order_info.created_at` | STRING | `data_criacao_recarga_info` | Data de Criação | Timestamp de criação do pedido | — |
| `order_info.created_by` | STRING | `usuario_criador_recarga_info` | Usuário Criador da Recarga | Usuário que criou o pedido | — |
| `order_info.updated_by` | STRING | `usuario_atualizacao_recarga_info` | Usuário Última Atualização | Usuário da última atualização | — |
| `order_info.order_status` | STRING | `status_recarga_info` | Status da Recarga | Status do pedido dentro do struct | idem `order_status` (mesmos 15 valores) |
| `order_info.company_group_id` | STRING | `id_grupo_recarga_info` | ID Grupo | UUID do grupo. **Segundo caminho de filtro multi-tenant** — o canônico é `company_group.id` | — |
| `order_info.distributed` | TIMESTAMP | `data_distribuicao_recarga_info` | Data de Distribuição | Momento da distribuição. Usado como filtro temporal fino | — |
| `order_info.payment_method` | STRING | `metodo_pagamento_recarga_info` | Método de Pagamento | Tipo de documento para pagamento da recarga | PIX, BOLETO, BALANCE, STARK_PAY (NULL possível) |
| `order_info.balance_usage` | STRING | `uso_saldo_recarga_info` | Uso de Saldo (Financeiro) | Uso de saldo no pagamento da recarga | NONE, FULL (NULL possível) |
| `order_info.custom_description` | STRING | `contexto_recarga_info` | Contexto da Recarga | Descrição livre informada no pedido | — |
| `order_info.distribute_on` | STRING | `metodo_agendamento_recarga_info` | Método de Agendamento | Data agendada para distribuir | SCHEDULED_DATE, ORDER_BOOKED (NULL possível) |
| `order_info.scheduled` | STRING | `data_agendada_recarga_info` | Data Agendada (Distribuição) | Indicação de agendamento do pedido | — |

### Detalhes da Recarga (granularidade de colaborador)

Campos no nível dos **detalhes da recarga** (`order_item_id`). Uma linha por detalhe.

#### Campos dos Detalhes da Recarga

| Coluna | Tipo | Alias PT-BR | Exibição | Descrição | Valores |
|--------|------|-------------|----------|-----------|--------|
| `order_item_id` | STRING | `id_item_recarga` | ID Item Recarga | ID do item de recarga. É a granularidade desta tabela (uma linha por item) | — |
| `order_item_status` | STRING | `status_item_recarga` | Status Item Recarga | Status do item da recarga | DISTRIBUTION_COMPLETE, CREATED, DISTRIBUTION_FAILED |
| `amount` | DOUBLE | `valor_item_recarga` | Valor da Recarga | Valor da recarga (R$) | — |
| `cashback_amount` | DOUBLE | `valor_cashback_item` | Valor Cashback | Valor do cashback (R$) | — |
| `employee_id` | STRING | `id_colaborador_recarga` | ID Colaborador | ID do funcionário | — |
| `person_id` | STRING | `id_usuario_iFB` | ID Usuário iFB | Person ID iFB |
| `product_key` | STRING | `saldo_ifood_item_recarga` | Benefício iFood | Benefício de recarga do item | FOOD_VOUCHER, MEAL_VOUCHER, REWARD_VOUCHER, FLEX_MEAL_VOUCHER, MOBILITY_VOUCHER, PHARMACY_VOUCHER, HOME_OFFICE_VOUCHER, CULTURE_VOUCHER, IFOOD_FLEX_MEAL_VOUCHER, PHARMACY_VOUCHER_V2, EDUCATION_VOUCHER (NULL possível) |
| `company` | STRUCT | `struct_empresa` | Dados Empresa | {id, name, cnpj} - Dados da companhia específica dentro do grupo | — |
| `order_item_info` | STRUCT | `struct_order_item` | Detalhes do Item de Recarga | Metadados do item | — |

> **Decisão registrada:** para **identificar/filtrar** um colaborador específico na
> recarga, use **somente** `person_id` (`id_usuario_iFB`). `employee_id` é a chave
> de JOIN com `employee.id` — **não** use `employee_id` para filtrar por CPF/personId
> (a conversão CPF→personId acontece antes de chegar aqui).

#### Campos dos Detalhes da Recarga — STRUCT company

| Coluna | Tipo | Alias PT-BR | Exibição | Descrição | Valores |
|--------|------|-------------|----------|-----------|--------|
| `company.id` | STRING | `id_empresa_recarga` | ID Empresa | UUID da empresa dentro do grupo | — |
| `company.name` | STRING | `nome_empresa_recarga` | Nome da Empresa | Nome da empresa | — |
| `company.cnpj` | STRING | `cnpj_empresa_recarga` | CNPJ da Empresa | CNPJ da empresa | — |

### Técnico / Partição

| Coluna | Tipo | Alias PT-BR | Exibição | Descrição | Valores |
|--------|------|-------------|----------|-----------|--------|
| `update_month` | STRING | `mes_atualizacao` | Mês de Atualização | Mês da atualização (YYYY-MM) | — |
| `update_date` | STRING | `data_atualizacao` | Data de Atualização | Partição diária (YYYY-MM-DD) | — |

> Os aliases PT-BR de `order_info.*` foram propostos aqui (não vinham do catálogo original)
> e os tipos ainda não foram confirmados — ajustar quando alguém validar no Databricks.

### Valores possíveis (enums)

#### Recarga — Status do pedido (`order_status` / `STATUSES`)

**Contexto:** status de recargas na listagem, detalhe e fluxo de criação (pré-pago). Coluna `order_status` em `ifood_benefits_recharges` (quando disponível).

| Enum | Tradução (TITLE) |
|------|------------------|
| `CREATED` | Em aberto |
| `SCHEDULED` | Em aberto |
| `BOOKING` | Agendando... |
| `BOOK_PENDING_PAYMENT` | A pagar |
| `BOOK_REJECTED` | Recarga bloqueada |
| `BOOK_FAILED` | Falha ao agendar |
| `BOOKED` | Agendada |
| `ANTICIPATING` | Antecipada |
| `DISTRIBUTING` | Distribuindo... |
| `DISTRIBUTION_IN_PROGRESS` | Na fila para distribuir |
| `DISTRIBUTION_FAILED` | Na fila para distribuir |
| `DISTRIBUTION_COMPLETE` | Distribuída |
| `DISTRIBUTION_INCOMPLETE` | Distribuição incompleta |
| `DISTRIBUTED` | Distribuída |
| `CANCELED` | Cancelada |
| `CANCELLING` | Cancelando... |
| `UNPAID_CANCELED` | Cancelada |
| `UNPAID_CANCELLING` | Cancelando... |

#### Recarga — Status pós-pago (`STATUSES_POS`)

**Contexto:** status de recargas para empresas com conta pós-paga.

| Enum | Tradução (TITLE) |
|------|------------------|
| `CREATED` | Programada |
| `PENDING` | Em aberto |
| `DRAFT` | Em aberto |
| `NOT_PROCESSED` | Em aberto |
| `CREATED_WITH_PENDECIES` | Em aberto |
| `DISTRIBUTED` | Distribuída |
| `CANCELED` | Cancelada |
| `FAILED` | Falha |
| `PROCESSING` | Processando |
| `PENDING_APPROVAL` | Aprovação pendente |

#### Recarga — Status do participante (`ParticipantStatus`) — coluna `order_item_status`

**Contexto:** status individual de cada colaborador dentro de uma recarga.

| Enum | Tradução |
|------|----------|
| `CREATED` | Em aberto |
| `CANCELED` | Cancelada |
| `DISTRIBUTION_COMPLETE` | Distribuída |
| `DISTRIBUTION_FAILED` | Não foi distribuída |

#### Recarga — Método de pagamento (`order_info.payment_method`)

**Contexto:** forma de pagamento da recarga (struct `order_info` em `ifood_benefits_recharges`).

| Enum | Tradução |
|------|----------|
| `PIX` | Pix |
| `BOLETO` | Boleto |
| `BALANCE` | Saldo |
| `STARK_PAY` | Stark Pay |

#### Recarga — Uso de saldo (`order_info.balance_usage`)

**Contexto:** indica se a recarga usou saldo da conta financeira (struct `order_info`).

| Enum | Tradução |
|------|----------|
| `NONE` | Sem uso de saldo |
| `FULL` | Uso total de saldo |

#### Recarga — Agendamento da distribuição (`order_info.distribute_on`)

**Contexto:** como a distribuição da recarga foi agendada (struct `order_info`).

| Enum | Tradução |
|------|----------|
| `SCHEDULED_DATE` | Data agendada |
| `ORDER_BOOKED` | Pedido agendado |
