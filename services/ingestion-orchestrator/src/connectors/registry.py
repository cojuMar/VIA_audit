from typing import Type

from ..connector_base import ConnectorBase

# Import all connector implementations
from .aws_cloudtrail import AWSCloudTrailConnector
from .google_workspace import GoogleWorkspaceAdminConnector
from .plaid import PlaidTransactionsConnector
from .quickbooks import QuickBooksLedgerConnector

CONNECTOR_REGISTRY: dict[str, Type[ConnectorBase]] = {
    "aws_cloudtrail": AWSCloudTrailConnector,
    "google_workspace_admin": GoogleWorkspaceAdminConnector,
    "plaid_transactions": PlaidTransactionsConnector,
    "quickbooks_ledger": QuickBooksLedgerConnector,
}


def get_connector_class(connector_type: str) -> Type[ConnectorBase]:
    cls = CONNECTOR_REGISTRY.get(connector_type)
    if cls is None:
        raise ValueError(
            f"Unknown connector type: {connector_type!r}. "
            f"Registered: {list(CONNECTOR_REGISTRY.keys())}"
        )
    return cls


def list_connector_types() -> list[str]:
    return list(CONNECTOR_REGISTRY.keys())
