# Relacionamentos entre tabelas

Só estas ligações são aceitas em `JOIN ... ON`; JOIN por qualquer outra coluna é rejeitado.

```
employee.id              ──> ifood_benefits_recharges.employee_id
employee.company_id      ──> companies.company_id

ifood_benefits_recharges.company_group.id ──> companies.company_group_id
ifood_benefits_recharges.company.id       ──> companies.company_id

receivable_assets.company_group_id   ──> companies.company_group_id
receivable_assets.receivable_asset_id ──> company_tax_invoice.receivable_asset_id

chargeback.company_id          ──> companies.company_id
chargeback.group_id            ──> (grupo corporativo)

chargeback_employee.chargeback_id ──> chargeback.id
chargeback_employee.employee_id   ──> employee.id

company_tax_invoice.company_id ──> companies.company_id
company_tax_invoice.group_id   ──> (grupo corporativo)

financial_transaction.account_id ──> financial_account.id
financial_account.group_id       ──> (grupo corporativo)
```

> A chave é sempre `tabela.coluna → tabela.coluna`, com o nome **físico** das duas pontas.
> `ifood_benefits_recharges` **não** tem `company_id` de topo — a ligação com empresa é pelo
> struct `company.id`, e com colaborador é por `employee_id`.

## Cruzamento recebível × nota fiscal (configurações de pagamento e faturamento)

Regra de negócio conceitual — afeta o cruzamento recebível ↔ nota fiscal.

| Cenário | Pagamento (PIX/boleto) | Nota fiscal | Efeito no cruzamento |
|---|---|---|---|
| 1. Pagamento único + faturamento único | matriz | matriz | 1:1; `company_cnpj` da NF = matriz |
| 2. Pagamento único + faturamento segmentado | matriz | por CNPJ (filiais) | `company_cnpj` da NF pode ser filial; filtrar por filial traz só a NF, sem o pagamento |
| 3. Pagamento segmentado + faturamento segmentado | por CNPJ | por CNPJ | `company_cnpj` da NF = CNPJ que pagou |

Implicação: ao cruzar `receivable_assets` ↔ `company_tax_invoice` via `receivable_asset_id`, o `company_cnpj` da NF identifica quem recebeu a NF (matriz ou filial), não necessariamente quem pagou. A NF é sempre emitida por saldo iFood (`product_type`), então um mesmo recebível pode gerar múltiplas NFs.
