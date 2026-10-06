"""Fase 1 — guardrails de borda: `group_id` como UUID e CNPJ/CPF sem máscara."""

from uuid import UUID

import pytest
from domain.agents.reports_b2b.guardrails import (
    InvalidGroupIdError,
    is_valid_group_id,
    normalize_cnpj_cpf,
    validate_group_id,
)

GROUP = "550e8400-e29b-41d4-a716-446655440000"


# ---------------------------------------------------------------- group_id --


def test_valid_uuid_returns_canonical():
    assert validate_group_id(GROUP) == GROUP


@pytest.mark.parametrize(
    "entry",
    [
        GROUP.upper(),
        f"  {GROUP}  ",
        "{550e8400-e29b-41d4-a716-446655440000}",
        "urn:uuid:550e8400-e29b-41d4-a716-446655440000",
        "550e8400e29b41d4a716446655440000",
        UUID(GROUP),
    ],
)
def test_equivalent_forms_normalize_to_same_uuid(entry):
    assert validate_group_id(entry) == GROUP


@pytest.mark.parametrize(
    "entry",
    [
        None,
        "",
        "   ",
        "unknown",
        "550e8400-e29b-41d4-a716",
        "550e8400-e29b-41d4-a716-44665544000g",
        123,
        ["550e8400-e29b-41d4-a716-446655440000"],
    ],
)
def test_invalid_group_id_is_rejected(entry):
    with pytest.raises(InvalidGroupIdError):
        validate_group_id(entry)


@pytest.mark.parametrize(
    "payload",
    [
        "' OR '1'='1",
        f"{GROUP}' OR '1'='1",
        f"{GROUP}'; DROP TABLE employee; --",
        f"{GROUP}' UNION SELECT * FROM employee --",
        f"{GROUP}' --",
    ],
)
def test_sql_injection_in_group_id_is_rejected(payload):
    """O único caminho de injection literal do fluxo: `... = '{group_id}'`."""
    with pytest.raises(InvalidGroupIdError):
        validate_group_id(payload)


def test_canonical_value_has_no_quotes_or_comment():
    canonical = validate_group_id(GROUP.upper())
    assert set(canonical) <= set("0123456789abcdef-")


def test_is_valid_group_id():
    assert is_valid_group_id(GROUP) is True
    assert is_valid_group_id("unknown") is False


# ------------------------------------------------------------ cnpj/cpf -----


def test_formatted_cnpj_becomes_digits():
    assert normalize_cnpj_cpf("CNPJ 12.345.678/0001-90") == "CNPJ 12345678000190"


def test_formatted_cpf_becomes_digits():
    assert normalize_cnpj_cpf("CPF 123.456.789-00") == "CPF 12345678900"


def test_cnpj_with_spaces_becomes_digits():
    assert normalize_cnpj_cpf("12 345 678 0001 90") == "12345678000190"


def test_alphanumeric_cnpj_becomes_uppercase_without_mask():
    assert normalize_cnpj_cpf("CNPJ 12.ABC.345/0001-90") == "CNPJ 12ABC345000190"


def test_lowercase_alphanumeric_cnpj_normalizes_to_uppercase():
    assert normalize_cnpj_cpf("cnpj 12.abc.345/0001-90") == "cnpj 12ABC345000190"


def test_date_is_not_normalized():
    assert normalize_cnpj_cpf("recargas de 2026-08-20") == "recargas de 2026-08-20"


def test_text_without_document_passes_intact():
    question = "Colaboradores ativos por empresa"
    assert normalize_cnpj_cpf(question) == question
