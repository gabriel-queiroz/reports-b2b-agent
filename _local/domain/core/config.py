class _Settings:
    """Qualquer configuração lida nos testes vem vazia."""

    def __getattr__(self, name):
        return ""


settings = _Settings()
