## 11. Financial Transaction (Transação Financeira)

**Local**: `main.ifood_benf_transaction_service.financial_transaction`

**Descrição**: Registro dos dados relativos às movimentações de valor na conta financeira da empresa cliente do iFood Benefícios (B2B). Exemplos: entradas a partir da adição de saldo para consumo em recargas futuras, entradas a partir de estornos de recarga, saídas a partir de distribuições de recargas.

**Frequência**: D-1

**Domínio**: `financeiro`

**Multi-tenant**: não possui coluna de grupo. Exige `INNER JOIN main.ifood_benf_transaction_service.financial_account fa ON financial_transaction.account_id = fa.id` e filtro em `fa.group_id`.

**Partição obrigatória**: nenhuma confirmada. O dump do Databricks não declara partição para esta tabela e não lista as colunas `dt`/`dt_partition` que o catálogo antigo citava. Não filtrar por elas — coluna inexistente quebra a query.

**Filtros padrão**: `deleted = false`, `test = false`.

### Colunas Principais

| Coluna | Tipo | Alias PT-BR | Exibição | Descrição | Valores |
|--------|------|-------------|----------|-----------|--------|
| `id` | STRING | `id_transacao_financeira` | Transação Financeira (ID) | UUID único da movimentação. Chave primária. | — |
| `account_id` | STRING | `id_conta_financeira_transacao` | Conta Financeira | FK para `financial_account.id`. | — |
| `amount` | DOUBLE | `valor_transacao` | Valor | Valor da movimentação (R$). | — |
| `amount_currency` | STRING | `moeda_valor` | Moeda | Moeda do valor (ex.: BRL). | BRL |
| `authorization_id` | STRING | `id_autorizacao` | Autorização | ID da autorização associada à movimentação. | — |
| `type` | STRING | `tipo_transacao` | Tipo | Tipo da movimentação (entrada, saída, estorno, etc.). | CREDIT, DEBIT |
| `rubric` | STRING | `rubrica` | Rubrica | Rubrica/classificação contábil da movimentação | DISTRIBUTION_WALLET, BILLING_PAID, DISTRIBUTION, REVERSAL_PAYMENT, TRANSFER, OCCURRENCE, SALES_BOOST, TRANSFER_REFUND |
| `justification` | STRING | `justificativa` | Justificativa | Justificativa/descrição da movimentação. | — |
| `transaction_date` | STRING | `data_transacao` | Data da Transação | Data da movimentação (YYYY-MM-DD). | — |
| `external_id` | STRING | `id_externo_transacao` | ID Externo | ID externo da movimentação. | — |
| `idempotence_id` | STRING | `id_idempotencia` | ID de Idempotência | Chave de idempotência da movimentação. | — |
| `is_synced` | BOOLEAN | `sincronizado` | Sincronizado | Indica se a movimentação foi sincronizada com sistemas externos. | — |
| `test` | BOOLEAN | `teste_transacao` | Teste | Flag de dados de teste. `true` = teste, `false` = produção. | — |
| `deleted` | BOOLEAN | `deletado_transacao` | Deletado | Soft delete. Filtrar `deleted = false`. | — |
| `created_at` | STRING | `data_criacao_transacao` | Data de Criação | Timestamp ISO 8601 de criação. | — |
| `updated_at` | STRING | `data_atualizacao_transacao` | Data de Atualização | Timestamp ISO 8601 da última atualização. | — |
| `_origin_time` | STRING | `tempo_origem` |  | Metadado técnico Databricks. Normalmente ignorado em relatórios. | — |
| `_processing_time` | STRING | `tempo_processamento` |  | Metadado técnico Databricks. Normalmente ignorado em relatórios. | — |
| `_timeid` | STRING | `timeid` |  | Metadado técnico de particionamento. Normalmente ignorado em relatórios. | — |

### Valores possíveis (enums)

#### Financeiro — Motivo de transação (`TransactionReasonEnum`) — coluna `financial_transaction.rubric`

| Enum | Tradução |
|------|----------|
| `TRANSFER_REFUND` | Devolução de saldo na plataforma |
| `REVERSAL_PAYMENT` | Reversão de pagamento |
| `DISTRIBUTION` | Distribuição de Recarga |
| `BILLING_PAID` | Pagamento faturado |
| `OCCURRENCE` | Ocorrência |
| `SALES_BOOST` | Campanha Promocional |
| `DISTRIBUTION_WALLET` | Distribuição de carteira |
| `TRANSFER` | Transferência |

#### Financeiro — Tipo de transação (`TransactionTypeEnum`) — coluna `financial_transaction.type`

| Enum | Tradução |
|------|----------|
| `CREDIT` | Crédito |
| `DEBIT` | Débito |
