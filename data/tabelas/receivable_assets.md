## 5. Receivable Assets (Pagamento)

**Local**: `main.fintech_finance.receivable_assets`

**Descrição**: Pagamentos (boletos, PIX e faturas) do iFood Benefícios. Uma linha por pagamento.

**Particionada por**: `asset_month` (YYYY-MM) - **OBRIGATÓRIA em WHERE**

**Domínio**: `financeiro`

**Multi-tenant**: coluna direta `company_group_id`. Não exige JOIN.

**Filtros padrão**: `deleted = false`.

**Enums**: o dump do Databricks lista `status` como `PENDING, RECEIVED, CANCELED, EXPIRED`. `OVERDUE` está documentado aqui como possível valor legado — ao filtrar por vencidos, considerar os dois. `STARK_PAY` é tipo válido.

**Colunas disponíveis**: exatamente as listadas abaixo — nenhuma outra.

### Colunas Principais

| Coluna | Tipo | Alias PT-BR | Exibição | Descrição | Valores |
|--------|------|-------------|----------|-----------|--------|
| `receivable_asset_id` | STRING | `id_pagamento` | ID Documento | UUID único do pagamento | — |
| `type` | STRING | `tipo_pagamento` | Tipo Pagamento | Método de pagamento do documento | PIX, BOLETO, STARK_PAY |
| `status` | STRING | `status_pagamento` | Status Pagamento | Status do pagamento | RECEIVED, CANCELED, PENDING, EXPIRED |
| `product_type` | STRING | `saldo_ifood_pagamento` | Benefício iFood | Benefício associado ao pagamento | REWARD_VOUCHER, MEAL_VOUCHER, FLEX_MEAL_VOUCHER, MULTIPLE, MOBILITY_VOUCHER, COLAB_MAIS, CARD_ISSUE, IFOOD_FLEX_MEAL_VOUCHER, HOME_OFFICE_VOUCHER, PHARMACY_VOUCHER, CULTURE_VOUCHER, DINEIN, EDUCATION_VOUCHER, PHARMACY_VOUCHER_V2 |
| `company_group_id` | STRING | `company_group_id` | ID Grupo | ID do grupo corporativo | — |
| `amount` | DOUBLE | `valor_pagamento` | Valor Pagamento | Valor principal (R$) | — |
| `due_date` | STRING | `data_vencimento` | Data Vencimento | Data de vencimento (YYYY-MM-DD) | — |
| `paid_at` | TIMESTAMP | `data_pagamento` | Data Pagamento | Timestamp do pagamento | — |
| `created_at` | TIMESTAMP | `data_criacao_pagamento` | Data de Emissão | Timestamp de criação | — |
| `asset_month` | STRING | `mes_pagamento` | Mês Emissão Documento | **Coluna de partição** (YYYY-MM). Filtrar sempre | — |
| `deleted` | BOOLEAN | `deletado_pagamento` |  | Soft delete. Filtrar `deleted = false` — **filtro apenas, não é campo de relatório**. | — |

### Valores possíveis (enums)

#### Financeiro — Status de pagamento (`StatusEnum`) — coluna `receivable_assets.status`

**Contexto:** aba Pagamentos no Financeiro, contas a receber e pagamentos de recarga.

| Enum | Label (UI) | Label alternativo (`STATUS_LABEL`) |
|------|------------|-------------------------------------|
| `PENDING` | A pagar | A pagar |
| `RECEIVED` | Compensado | Compensado |
| `EXPIRED` | Expirado | Expirado |
| `CANCELED` | Cancelado | Cancelado |

#### Financeiro — Método de pagamento (`PaymentMethodEnum`) — coluna `receivable_assets.type`

| Enum | Tradução |
|------|----------|
| `PIX` | Pix |
| `BOLETO` | Boleto |
| `STARK_PAY` | Stark Pay |
