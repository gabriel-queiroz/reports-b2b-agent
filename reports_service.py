"""Reports service executor: calls external API to execute SQL queries."""

from typing import Any

import httpx

from domain.core.config import settings
from domain.core.ioc import get_logger

logger = get_logger()


async def generate_reports(
    sql: str, group_id: str = None, user_id: str = None
) -> dict[str, Any]:
    """Call Reports Service API to request report generation.

    Args:
        sql: SQL query to execute (already validated with group_id filter)
        group_id: groupId validation - company group UUID (mandatory for security)
        user_id: User UUID responsible for the request

    Returns:
        Dict with API response: {"id": "report_uuid"}

    Raises:
        ValueError: If group_id or user_id is missing
        Exception: If API call fails
    """
    # groupId validation: group_id and user_id are required for security
    if not group_id:
        logger.log_error("Missing group_id for multi-tenant security", ValueError())
        raise ValueError("groupId validation failed: group_id is mandatory")

    if not user_id:
        logger.log_error("Missing user_id for audit trail", ValueError())
        raise ValueError("user_id is mandatory for audit trail")

    try:
        # Get reports service base URL and requester token from config
        reports_service_base_url = settings.reports_service_api_url
        if not reports_service_base_url:
            logger.log_error("REPORTS_SERVICE_API_URL not configured", ValueError())
            raise ValueError("REPORTS_SERVICE_API_URL not configured in settings")

        requester_token = settings.requester_token
        if not requester_token:
            logger.log_error("REQUESTER_TOKEN not configured", ValueError())
            raise ValueError("REQUESTER_TOKEN not configured in settings")

        # Build full endpoint URL (base + path)
        reports_service_url = (
            reports_service_base_url.rstrip("/") + "/v1/reports/ai-report"
        )

        # Call Reports Service API with camelCase field names
        # (groupId validation at API layer)
        headers = {"x-requester-token": requester_token}
        payload = {
            "query": sql,
            "groupId": group_id,
            "userId": user_id,
        }

        logger.log_information(
            "Calling Reports Service API",
            query_tail=sql[-30:],
        )

        async with httpx.AsyncClient(
            timeout=settings.reports_service_timeout
        ) as client:
            response = await client.post(
                reports_service_url,
                json=payload,
                headers=headers,
            )

        logger.log_information(
            "Reports Service response received",
            status_code=response.status_code,
        )

        if response.status_code != 200:
            logger.log_error(
                "Reports API returned error",
                Exception(response.text),
                status_code=response.status_code,
            )
            response.raise_for_status()

        result = response.json()
        logger.log_information(
            "Report generation requested",
            report_id=result.get("id"),
        )
        return result

    except Exception as e:
        logger.log_error("Failed to request report generation", e)
        raise
