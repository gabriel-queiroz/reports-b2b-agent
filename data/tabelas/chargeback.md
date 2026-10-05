## 6. Chargeback (Estornos)

**Local**: `main.ifoodoffice_recharge_chargeback.chargeback`

**Descrição**: Estornos de recargas.

**Domínio**: `estorno_recarga` — estorno de recargas.

**Multi-tenant**: coluna direta `group_id` — **confirmado que é o UUID do grupo de empresas**, mesmo valor de `companies.company_group_id`. Filtrar `chargeback.group_id = '<uuid>'`. **JOIN com `companies` não é necessário.**

**Partição obrigatória**: `updated_at` (confirmado que a coluna existe). Confirmar se é de fato a coluna de partição.

**Filtros padrão**: nenhum — esta tabela não tem `deleted` nem `test`.

### Estorno (granularidade de empresa)

| Coluna | Tipo | Alias PT-BR | Exibição | Descrição |
|--------|------|-------------|----------|-----------|
| `id` | STRING | `id_estorno` | ID Estorno | UUID único para cada requisição de chargeback |
| `company_id` | STRING | `id_empresa` | ID Empresa | UUID de identificação da empresa cliente |
| `company_name` | STRING | `nome_empresa` | Nome Empresa | Nome oficial da empresa registrada |
| `group_id` | STRING | `id_grupo` | ID Grupo | UUID do grupo de empresas (multi-tenant) |
| `login` | STRING | `email_solicitante_estorno` | Email Solicitante | Email do usuário que solicitou o estorno |
| `chargeback_status` | STRING | `status_estorno` | Status Estorno | Status do estorno. Ver enum `ChargebackStatusEnum` na seção de enums. |
| `total_amount_requested` | DOUBLE | `valor_total_solicitado` | Valor Total Solicitado | Valor total solicitado em BRL (pré-validação) |
| `total_amount_recharged` | DOUBLE | `valor_total_estornado` | Valor Total Estornado | Valor total efetivamente estornado em BRL |
| `total_chargeback_employees` | BIGINT | `total_colaboradores_estorno` | Total de Colaboradores | Total de colaboradores na requisição |
| `updated_at` | STRING | `data_estorno` | Data Estorno | Timestamp ISO 8601 da última atualização |

### Valores possíveis (enums)

#### Estorno de recarga — Status (`ChargebackStatusEnum`) — coluna `chargeback_status`

| Enum | Tradução |
|------|----------|
| `CONCLUDED` | Concluído |
| `PROCESSING` | Em processamento |
