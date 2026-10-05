# Enums compartilhados

Valores de colunas que existem em mais de uma tabela. A tool `get_table_schema` anexa cada bloco ao schema das tabelas que têm alguma das colunas citadas no título (depois de `coluna`/`colunas`, entre crases).

### Produtos (`ProductsEnum`) — colunas `product_key`, `product_type`

**Contexto:** tipo de benefício/saldo em recargas, financeiro, estornos e relatórios.

| Enum | Tradução (TITLE) | Descrição (DESCRIPTION) |
|------|------------------|-------------------------|
| `FOOD_VOUCHER` | Alimentação (PAT) | Supermercados, Açougues, Padarias e Hortifrútis |
| `MEAL_VOUCHER` | Refeição (PAT) | Aplicativos de delivery, Lanchonetes e Restaurantes |
| `PAT` | Refeição & Alimentação (PAT) | Mercados, açougues, mercearias, aplicativos de entrega, padarias, restaurantes e lanchonetes |
| `FOOD` | Alimentação (PAT) | Supermercados, Açougues, Padarias e Hortifrútis |
| `MEAL` | Refeição (PAT) | Aplicativos de delivery, Lanchonetes e Restaurantes |
| `REWARD_VOUCHER` | Saldo Livre | Para o seu colaborador utilizar onde quiser |
| `MOBILITY_VOUCHER` | Mobilidade | Cartão de transporte público, apps de mobilidade, gasolina |
| `EDUCATION_VOUCHER` | Educação | Cursos online, cursos de idiomas, técnico e ensino superior |
| `CULTURE_VOUCHER` | Cultura | Livrarias, cinemas, teatros, serviços de streaming, Ebooks |
| `HOME_OFFICE_VOUCHER` | Home Office | Papelaria, mobiliário, equipamentos de informática |
| `PHARMACY_VOUCHER` | Saúde e Bem-estar | Farmácias, academias, exames médicos e apps |
| `PHARMACY_VOUCHER_V2` | Farmácia | Medicamentos, higiene pessoal, cosméticos e mais |
| `FLEX_MEAL_VOUCHER` | Alimentação+Refeição (Não-PAT) | Supermercados, restaurantes e similares |
| `IFOOD_FLEX_MEAL_VOUCHER` | Comer no iFood | Para usar em refeição e alimentação no app do iFood |
| `IFOOD_CARD` | iFood Card | Cartão de benefícios do iFood |
| `IFOOD_CORP` | iFood Corporativo | Benefício corporativo iFood |
| `DEBT_RENEGOTIATION` | Renegociação | Renegociação de débitos |
| `CARD_ISSUE` | Cobrança de Cartões | Cobrança de Cartões |
| `MULTIPLE` | Multibenefícios | Multibenefícios |
| `COLAB_MAIS` | Colab+ | Colab+ |
| `POSTPAID` | Pós-pago | Outros saldos |
| `DINEIN` | Comer fora | Comer fora |
