## 10. Financial Account (Conta Financeira)

**Local**: `main.ifood_benf_transaction_service.financial_account`

**Descrição**: Registro dos dados técnicos relativos à conta financeira da empresa cliente do iFood Benefícios (B2B). É a conta que viabiliza as movimentações de valor no Financeiro da Plataforma iFood Benefícios.

**Frequência**: D-1

**Domínio**: `financeiro`

**Multi-tenant**: coluna direta `group_id` (atenção: **não** se chama `company_group_id`). Não exige JOIN.

**Partição obrigatória**: nenhuma documentada.

**Filtros padrão**: `deleted = false`, `test = false`.

### Colunas Principais

| Coluna | Tipo | Alias PT-BR | Exibição | Descrição | Valores |
|--------|------|-------------|----------|-----------|--------|
| `id` | STRING | `id_conta_financeira_conta` | Conta Financeira (ID) | UUID único da conta financeira da empresa cliente. Chave primária. | — |
| `group_id` | STRING | `id_grupo_conta` | Grupo | UUID do grupo corporativo da empresa. **Usar para filtros multi-tenant.** | — |
| `product_type` | STRING | `tipo_produto_conta` | Tipo de Produto | Produto ao qual a conta está vinculada | MEAL_VOUCHER, REWARD_VOUCHER, MOBILITY_VOUCHER, PHARMACY_VOUCHER, CULTURE_VOUCHER, EDUCATION_VOUCHER, HOME_OFFICE_VOUCHER, FLEX_MEAL_VOUCHER, IFOOD_FLEX_MEAL_VOUCHER, PHARMACY_VOUCHER_V2, FOOD_VOUCHER, IFOOD_CARD, IFOOD_CORP |
| `type` | STRING | `tipo_conta` | Tipo | Tipo da conta financeira | MAIN, OCCURRENCE, BOOKING, REBATE, CASHBACK, MAIN_INVOICED_BOLETO |
| `origin` | STRING | `origem` | Origem | Origem de criação da conta financeira | COMPANY, MOVILE_WALLET, IFOOD_BENEFITS, IFOOD_BENEFITS_PROFIT, IFOOD_OCCURRENCE, IFOOD_CASHBACK, IFOOD_REBATE, IFOOD_MEALVOUCHER_OCCURRENCE |
| `created_at` | STRING | `data_criacao_conta` | Data de Criação | Timestamp ISO 8601 de criação da conta. | — |
| `updated_at` | STRING | `data_atualizacao_conta` | Data de Atualização | Timestamp ISO 8601 da última atualização da conta. | — |
| `test` | BOOLEAN | `teste_conta` |  | Flag de dados de teste. `true` = teste, `false` = produção — **filtro apenas, não é campo de relatório**. | — |
| `deleted` | BOOLEAN | `deletado_conta` |  | Soft delete. Filtrar `deleted = false` — **filtro apenas, não é campo de relatório**. | — |

### Valores possíveis (enums)

#### Financeiro — Tipo de conta da empresa (`CompanyAccountTypeEnum`) — coluna `financial_account.type`

| Enum | Descrição |
|------|-----------|
| `MAIN` | Principal |
| `OCCURRENCE` | Ocorrência |
| `BOOKING` | Agendamento |
| `REBATE` | Rebate |
| `CASHBACK` | Cashback |
| `MAIN_INVOICED_BOLETO` | Principal (boleto faturado) |

#### Financeiro — Origem da conta financeira (`financial_account.origin`)

**Contexto:** origem de criação da conta financeira.

| Enum | Tradução |
|------|----------|
| `COMPANY` | Empresa |
| `MOVILE_WALLET` | Carteira Movile |
| `IFOOD_BENEFITS` | iFood Benefícios |
| `IFOOD_BENEFITS_PROFIT` | iFood Benefícios (lucro) |
| `IFOOD_OCCURRENCE` | iFood Ocorrência |
| `IFOOD_CASHBACK` | iFood Cashback |
| `IFOOD_REBATE` | iFood Rebate |
| `IFOOD_MEALVOUCHER_OCCURRENCE` | iFood Ocorrência de Vale-Refeição |
