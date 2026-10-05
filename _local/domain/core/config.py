class _Settings:
    """Qualquer configuração lida nos testes vem vazia."""

    def __getattr__(self, nome):
        return ""


settings = _Settings()
