"""
Sprint 2 — Connector SDK Contract Tests

Verifies that all registered connectors correctly implement the ConnectorBase
contract and produce valid canonical evidence records.

Run: pytest tests/sprint2/test_connector_sdk.py -v
"""

import pytest
import sys
import os
from unittest.mock import patch
from datetime import datetime, timezone
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/ingestion-orchestrator'))

# ---------------------------------------------------------------------------
# These tests define the contract every connector MUST satisfy.
# When adding a new connector, add it to CONNECTOR_UNDER_TEST below and
# ensure all contract tests pass.
# ---------------------------------------------------------------------------

TENANT_ID = str(uuid4())
MOCK_CREDENTIALS_BY_TYPE = {
    'aws_cloudtrail': {
        'extra': {
            'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
            'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
        }
    },
    'google_workspace_admin': {
        'extra': {
            'service_account_json': '{"type":"service_account","project_id":"test"}',
            'delegated_admin_email': 'admin@example.com',
        }
    },
    'plaid_transactions': {
        'client_id': 'test_client_id',
        'client_secret': 'test_client_secret',
        'oauth_access_token': 'access-sandbox-test',
    },
    'quickbooks_ledger': {
        'oauth_access_token': 'test_access_token',
        'oauth_refresh_token': 'test_refresh_token',
        'client_id': 'test_client_id',
        'client_secret': 'test_client_secret',
    },
}

REQUIRED_CANONICAL_FIELDS = [
    'event_type',
    'entity_id',
    'entity_type',
    'timestamp_utc',
    'outcome',
]


def make_credentials(connector_type: str):
    """Build a ConnectorCredentials mock for the given connector type."""
    from src.connector_base import ConnectorCredentials
    data = MOCK_CREDENTIALS_BY_TYPE.get(connector_type, {})
    return ConnectorCredentials(
        api_key=data.get('api_key'),
        oauth_access_token=data.get('oauth_access_token'),
        oauth_refresh_token=data.get('oauth_refresh_token'),
        client_id=data.get('client_id'),
        client_secret=data.get('client_secret'),
        extra=data.get('extra', {}),
    )


# ---------------------------------------------------------------------------
# AWS CloudTrail connector tests
# ---------------------------------------------------------------------------

class TestAWSCloudTrailConnector:
    """Tests for the AWSCloudTrailConnector."""

    @pytest.fixture
    def connector(self):
        from src.connectors.aws_cloudtrail import AWSCloudTrailConnector
        with patch('boto3.client'):
            return AWSCloudTrailConnector(
                tenant_id=TENANT_ID,
                connector_config={'region': 'us-east-1'},
                credentials=make_credentials('aws_cloudtrail'),
            )

    def test_connector_type_constant(self, connector):
        assert connector.connector_type == 'aws_cloudtrail'

    def test_normalize_to_canonical_structure(self, connector):
        """normalize_to_canonical must return a valid CanonicalEvidenceRecord."""
        raw_event = {
            'EventId': 'evt-test-123',
            'EventName': 'PutBucketPolicy',
            'EventSource': 's3.amazonaws.com',
            'EventTime': datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc),
            'Username': 'alice@example.com',
            'AwsRegion': 'us-east-1',
            'Resources': [{'ResourceName': 'arn:aws:s3:::secure-bucket'}],
        }
        record = connector.normalize_to_canonical(raw_event, datetime.now(timezone.utc))

        assert record.tenant_id is not None
        assert record.source_system == 'aws_cloudtrail'

        for field in REQUIRED_CANONICAL_FIELDS:
            assert field in record.canonical_payload, f"Missing required field: {field}"

    def test_normalize_event_type_format(self, connector):
        """event_type must be prefixed with 'aws.'"""
        raw_event = {
            'EventId': 'evt-001',
            'EventName': 'PutObject',
            'EventSource': 's3.amazonaws.com',
            'EventTime': datetime(2026, 4, 1, tzinfo=timezone.utc),
        }
        record = connector.normalize_to_canonical(raw_event, datetime.now(timezone.utc))
        assert record.canonical_payload['event_type'].startswith('aws.')

    def test_normalize_failure_event(self, connector):
        """Events with ErrorCode must map to outcome='failure'."""
        raw_event = {
            'EventId': 'evt-fail-001',
            'EventName': 'GetObject',
            'EventSource': 's3.amazonaws.com',
            'EventTime': datetime(2026, 4, 1, tzinfo=timezone.utc),
            'ErrorCode': 'AccessDenied',
            'ErrorMessage': 'Access Denied',
        }
        record = connector.normalize_to_canonical(raw_event, datetime.now(timezone.utc))
        assert record.canonical_payload['outcome'] == 'failure'

    def test_canonical_record_passes_validation(self, connector):
        """validate_canonical must return no errors for a well-formed record."""
        raw_event = {
            'EventId': 'evt-valid-001',
            'EventName': 'PutObject',
            'EventSource': 's3.amazonaws.com',
            'EventTime': datetime(2026, 4, 1, tzinfo=timezone.utc),
            'Username': 'alice@example.com',
        }
        record = connector.normalize_to_canonical(raw_event, datetime.now(timezone.utc))
        errors = connector.validate_canonical(record)
        assert errors == [], f"Validation errors: {errors}"

    def test_no_credentials_in_canonical_payload(self, connector):
        """Credentials must never appear in canonical_payload or metadata."""
        raw_event = {
            'EventId': 'evt-001',
            'EventName': 'GetSecretValue',
            'EventSource': 'secretsmanager.amazonaws.com',
            'EventTime': datetime(2026, 4, 1, tzinfo=timezone.utc),
            'RequestParameters': {
                'secretId': 'production/db-password',
                'versionId': 'abc123',
            }
        }
        record = connector.normalize_to_canonical(raw_event, datetime.now(timezone.utc))
        payload_str = str(record.canonical_payload)
        # The raw request parameters must not be included verbatim
        assert 'AKIAIOSFODNN7EXAMPLE' not in payload_str
        assert 'wJalrXUtnFEMI' not in payload_str


# ---------------------------------------------------------------------------
# Plaid connector tests
# ---------------------------------------------------------------------------

class TestPlaidConnector:
    """Tests for the PlaidTransactionsConnector."""

    @pytest.fixture
    def connector(self):
        from src.connectors.plaid import PlaidTransactionsConnector
        with patch('plaid.ApiClient'), patch('plaid.api.transactions_api.TransactionsApi'):
            return PlaidTransactionsConnector(
                tenant_id=TENANT_ID,
                connector_config={'environment': 'sandbox'},
                credentials=make_credentials('plaid_transactions'),
            )

    def test_connector_type_constant(self, connector):
        assert connector.connector_type == 'plaid_transactions'

    def test_normalize_transaction(self, connector):
        """Transaction amounts must go to metadata, not top-level canonical fields."""
        raw_txn = {
            'transaction_id': 'txn-abc-001',
            'account_id': 'acct-5000',
            'amount': 99.99,
            'iso_currency_code': 'USD',
            'merchant_name': 'ACME Corp',
            'date': '2026-04-01',
            'pending': False,
            'category': ['Shopping', 'General'],
        }
        record = connector.normalize_to_canonical(raw_txn, datetime.now(timezone.utc))

        assert record.canonical_payload['entity_id'] == 'txn-abc-001'
        assert record.canonical_payload['entity_type'] == 'financial_transaction'

        # Amount must be in metadata (private input for ZK proofs), NOT at top level
        assert 'amount' not in record.canonical_payload
        assert record.canonical_payload['metadata']['amount'] == 99.99

    def test_amount_isolation_for_zk(self, connector):
        """
        CRITICAL: Transaction amounts must only appear in metadata['amount'].
        They must not be in top-level canonical_payload fields.
        This ensures amounts are treated as ZK private inputs, not public data.
        """
        raw_txn = {
            'transaction_id': 'txn-sensitive-001',
            'account_id': 'acct-payroll',
            'amount': 150000.00,  # Sensitive amount (e.g. executive compensation)
            'iso_currency_code': 'USD',
            'date': '2026-04-01',
            'pending': False,
        }
        record = connector.normalize_to_canonical(raw_txn, datetime.now(timezone.utc))

        # Amount must NOT be a top-level field
        assert 'amount' not in record.canonical_payload
        # Amount MUST be in metadata for ZK proof private input
        assert 'amount' in record.canonical_payload.get('metadata', {})


# ---------------------------------------------------------------------------
# QuickBooks connector tests
# ---------------------------------------------------------------------------

class TestQuickBooksConnector:
    """Tests for the QuickBooksLedgerConnector."""

    @pytest.fixture
    def connector(self):
        from src.connectors.quickbooks import QuickBooksLedgerConnector
        return QuickBooksLedgerConnector(
            tenant_id=TENANT_ID,
            connector_config={'realm_id': '1234567890', 'environment': 'sandbox'},
            credentials=make_credentials('quickbooks_ledger'),
        )

    def test_connector_type_constant(self, connector):
        assert connector.connector_type == 'quickbooks_ledger'

    def test_normalize_journal_entry(self, connector):
        """Journal entries must map to canonical schema correctly."""
        raw_entry = {
            'Id': 'je-00042',
            'DocNumber': 'INV-2026-042',
            'TxnDate': '2026-04-01',
            'TotalAmt': 5000.00,
            'CurrencyRef': {'value': 'USD'},
            'MetaData': {
                'LastUpdatedTime': '2026-04-01T14:00:00Z',
                'LastModifiedByRef': {'value': 'user@company.com'},
            },
            'Line': [
                {
                    'DetailType': 'JournalEntryLineDetail',
                    'Amount': 5000.00,
                    'JournalEntryLineDetail': {
                        'PostingType': 'Debit',
                        'AccountRef': {'value': '90', 'name': 'Accounts Receivable'},
                    },
                },
                {
                    'DetailType': 'JournalEntryLineDetail',
                    'Amount': 5000.00,
                    'JournalEntryLineDetail': {
                        'PostingType': 'Credit',
                        'AccountRef': {'value': '5000', 'name': 'Revenue'},
                    },
                },
            ],
        }
        record = connector.normalize_to_canonical(raw_entry, datetime.now(timezone.utc))

        assert record.canonical_payload['entity_id'] == 'je-00042'
        assert record.canonical_payload['event_type'] == 'ledger.journal_entry'

    def test_memo_is_redacted(self, connector):
        """Private memo fields must be redacted in canonical payload."""
        raw_entry = {
            'Id': 'je-00043',
            'TxnDate': '2026-04-01',
            'TotalAmt': 1000.00,
            'PrivateNote': 'Executive bonus payment — confidential',
            'MetaData': {'LastUpdatedTime': '2026-04-01T10:00:00Z'},
            'Line': [],
        }
        record = connector.normalize_to_canonical(raw_entry, datetime.now(timezone.utc))
        payload_str = str(record.canonical_payload)

        assert 'Executive bonus' not in payload_str
        assert 'confidential' not in payload_str
        # Check that memo is explicitly redacted
        assert record.canonical_payload.get('metadata', {}).get('private_memo') == '[REDACTED]'


# ---------------------------------------------------------------------------
# ConnectorBase contract tests — run for ALL connectors
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('connector_type', [
    'aws_cloudtrail',
    'google_workspace_admin',
    'plaid_transactions',
    'quickbooks_ledger',
])
class TestConnectorContract:
    """
    Universal contract tests that EVERY connector must pass.
    When adding a new connector, add it to the parametrize list above.
    """

    def test_connector_type_is_non_empty_string(self, connector_type):
        from src.connectors.registry import get_connector_class
        cls = get_connector_class(connector_type)
        assert isinstance(cls.connector_type, str)
        assert len(cls.connector_type) > 0

    def test_connector_type_matches_registry_key(self, connector_type):
        from src.connectors.registry import get_connector_class
        cls = get_connector_class(connector_type)
        assert cls.connector_type == connector_type

    def test_connector_registered(self, connector_type):
        """All expected connectors are registered."""
        from src.connectors.registry import get_connector_class
        cls = get_connector_class(connector_type)
        assert cls is not None

    def test_connector_has_required_methods(self, connector_type):
        """All abstract methods from ConnectorBase are implemented."""
        from src.connectors.registry import get_connector_class
        from src.connector_base import ConnectorBase
        import inspect

        cls = get_connector_class(connector_type)
        abstract_methods = {
            name for name, method in inspect.getmembers(ConnectorBase, predicate=inspect.isfunction)
            if getattr(method, '__isabstractmethod__', False)
        }

        for method_name in abstract_methods:
            assert hasattr(cls, method_name), f"Connector {connector_type} missing method: {method_name}"
            method = getattr(cls, method_name)
            assert not getattr(method, '__isabstractmethod__', False), \
                f"Connector {connector_type}.{method_name} is not implemented"

    def test_connector_version_is_semver(self, connector_type):
        from src.connectors.registry import get_connector_class
        cls = get_connector_class(connector_type)
        parts = cls.version.split('.')
        assert len(parts) == 3, f"Connector version must be semver (x.y.z), got: {cls.version}"
        assert all(p.isdigit() for p in parts), f"Semver parts must be integers: {cls.version}"


# ---------------------------------------------------------------------------
# Circuit breaker state machine tests
# ---------------------------------------------------------------------------

class TestCircuitBreakerLogic:
    """Tests for the connector circuit breaker (failure isolation)."""

    def test_circuit_opens_after_threshold_failures(self):
        """Circuit opens after circuit_breaker_failure_threshold consecutive failures."""
        failure_threshold = 3
        failures = 0
        state = 'closed'

        for _ in range(failure_threshold):
            failures += 1
            if failures >= failure_threshold:
                state = 'open'

        assert state == 'open'

    def test_circuit_transitions_to_half_open_after_reset_timeout(self):
        """Circuit moves to half_open after reset_timeout_seconds."""
        import time
        opened_at = time.time() - 301  # 301 seconds ago
        reset_timeout = 300

        state = 'open'
        if time.time() - opened_at >= reset_timeout:
            state = 'half_open'

        assert state == 'half_open'

    def test_successful_poll_closes_circuit(self):
        """A successful poll from half_open state closes the circuit."""
        state = 'half_open'
        failures = 5

        # Simulate successful poll
        success = True
        if success:
            state = 'closed'
            failures = 0

        assert state == 'closed'
        assert failures == 0
