## 9. Company Tax Invoice (Notas Fiscais)

**Local**: `main.ifoodoffice_invoice_service.company_tax_invoice`

**Descrição**: Notas fiscais (NF-e/NFS-e) emitidas para empresas clientes.

**Domínio**: `financeiro`

**Multi-tenant**: coluna direta `group_id` — **confirmado que é o UUID do grupo de empresas**. Filtrar `company_tax_invoice.group_id = '<uuid>'`. **JOIN com `companies` não é necessário** (segue útil quando o relatório precisar do nome da empresa).

> `group_id` é **nulo para empresas sem grupo**. O filtro por grupo nunca casa com nulo, então notas de empresa avulsa não aparecem em relatório por grupo — que é o comportamento esperado do isolamento.

⚠️ **Correção pendente no código**: mesma do chargeback — `_has_valid_group_id_filter` não reconhece `group_id` puro para esta tabela.

**Partição obrigatória**: nenhuma documentada.

**Filtros padrão**: `deleted = false`.

### Colunas Principais

| Coluna | Tipo | Alias PT-BR | Exibição | Descrição | Valores |
|--------|------|-------------|----------|-----------|--------|
| `id` | STRING | `id_nf` | ID Nota Fiscal | UUID da nota | — |
| `company_id` | STRING | `id_empresa_nf` | ID Empresa | UUID da empresa | — |
| `company_cnpj` | STRING | `cnpj_empresa_nf` | CNPJ Empresa | CNPJ (14 dígitos) | — |
| `group_id` | STRING | `id_grupo_nf` | ID Grupo | UUID do grupo | — |
| `receivable_asset_id` | STRING | `id_pagamento_nf` | ID Documento Pagamento | FK para receivable_assets | — |
| `tax_invoice_status` | STRING | `status_nf` | Status Nota Fiscal | PENDING, AVAILABLE | AVAILABLE, PENDING |
| `tax_invoice_url` | STRING | `link_nf` | Link Nota Fiscal | URL para download | — |
| `product_type` | STRING | `saldo_ifood_nf` | Benefício iFood | Benefício da nota fiscal | MEAL_VOUCHER, REWARD_VOUCHER, FLEX_MEAL_VOUCHER, MOBILITY_VOUCHER, COLAB_MAIS, HOME_OFFICE_VOUCHER, CARD_ISSUE, PHARMACY_VOUCHER, CULTURE_VOUCHER, IFOOD_FLEX_MEAL_VOUCHER, EDUCATION_VOUCHER, DINEIN, PHARMACY_VOUCHER_V2, DEBT_RENEGOTIATION, IFOOD_CARD (NULL possível) |
| `amount` | DOUBLE | `valor_nf` | Valor Nota Fiscal | Valor em R$ | — |
| `created_at` | STRING | `data_solicitacao_nf` | Data Solicitação NF | Criação | — |
| `updated_at` | STRING | `data_emissao_nf` | Data Emissão NF | Timestamp ISO da última modificação | — |
| `deleted` | BOOLEAN | `deletado_nota` |  | Soft delete. Filtrar `deleted = false` — **filtro apenas, não é campo de relatório**. | — |

### Valores possíveis (enums)

#### Financeiro — Status de nota fiscal (`InvoiceStatusEnum`) — coluna `tax_invoice_status`

| Enum | Tradução |
|------|----------|
| `PENDING` | Não Disponível |
| `AVAILABLE` | Disponível |
