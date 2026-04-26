import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/monitoring-service"))


from src.cloud_config_checker import CloudConfigChecker
from src.models import CloudResourceConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_s3(resource_id, config, name=None):
    return CloudResourceConfig(
        provider="aws",
        resource_type="s3_bucket",
        resource_id=resource_id,
        resource_name=name or resource_id,
        region="us-east-1",
        config=config,
    )


def make_sg(resource_id, config, name=None):
    return CloudResourceConfig(
        provider="aws",
        resource_type="security_group",
        resource_id=resource_id,
        resource_name=name or resource_id,
        region="us-east-1",
        config=config,
    )


def make_iam(resource_id, config, name=None):
    return CloudResourceConfig(
        provider="aws",
        resource_type="iam_user",
        resource_id=resource_id,
        resource_name=name or resource_id,
        region=None,
        config=config,
    )


checker = CloudConfigChecker()


# ---------------------------------------------------------------------------
# TestCloudConfigChecker
# ---------------------------------------------------------------------------

class TestCloudConfigChecker:

    def test_s3_public_read_write_is_critical(self):
        """config={'acl': 'public-read-write'} → critical finding."""
        resource = make_s3("my-bucket", {"acl": "public-read-write"})
        findings = checker.check_resources([resource])
        assert findings, "Expected at least one finding"
        critical = [f for f in findings if f.severity == "critical"]
        assert critical, "Expected a critical finding for public-read-write ACL"

    def test_s3_public_read_is_high(self):
        """config={'acl': 'public-read'} → high finding."""
        resource = make_s3("my-bucket", {"acl": "public-read"})
        findings = checker.check_resources([resource])
        assert findings, "Expected at least one finding"
        high_sev = [f for f in findings if f.severity == "high"]
        assert high_sev, "Expected a high-severity finding for public-read ACL"

    def test_s3_blocked_public_access_no_finding(self):
        """config with block_public_acls and block_public_policy → no finding."""
        resource = make_s3(
            "safe-bucket",
            {
                "public_access_block": {
                    "block_public_acls": True,
                    "block_public_policy": True,
                }
            },
        )
        findings = checker.check_resources([resource])
        # block_public_acls is True → no block_public_acls finding; no ACL override
        acl_findings = [f for f in findings if f.finding_type == "cloud_s3_public_access"]
        assert len(acl_findings) == 0, "No S3 public access finding expected when public access is blocked"

    def test_sg_open_ssh_is_critical(self):
        """config with port 22 open to 0.0.0.0/0 → critical finding."""
        resource = make_sg(
            "sg-ssh",
            {"inbound_rules": [{"cidr": "0.0.0.0/0", "port": 22, "protocol": "tcp"}]},
        )
        findings = checker.check_resources([resource])
        assert findings, "Expected at least one finding"
        critical = [f for f in findings if f.severity == "critical"]
        assert critical, "Expected a critical finding for open SSH port"

    def test_sg_open_http_is_high(self):
        """Port 8080 open to 0.0.0.0/0 → high (not critical, since not 22/3389)."""
        resource = make_sg(
            "sg-8080",
            {"inbound_rules": [{"cidr": "0.0.0.0/0", "port": 8080, "protocol": "tcp"}]},
        )
        findings = checker.check_resources([resource])
        assert findings, "Expected at least one finding for port 8080 open to world"
        high = [f for f in findings if f.severity == "high"]
        assert high, "Expected a high-severity finding for port 8080"
        critical = [f for f in findings if f.severity == "critical"]
        assert not critical, "Port 8080 should not be critical (not SSH/RDP)"

    def test_sg_http_443_allowed(self):
        """Port 443 open to 0.0.0.0/0 → no finding (443 is allowed)."""
        resource = make_sg(
            "sg-https",
            {"inbound_rules": [{"cidr": "0.0.0.0/0", "port": 443, "protocol": "tcp"}]},
        )
        findings = checker.check_resources([resource])
        sg_findings = [f for f in findings if f.finding_type == "cloud_security_group_open"]
        assert len(sg_findings) == 0, "Port 443 should not generate a security group finding"

    def test_iam_mfa_disabled_is_high(self):
        """config={'mfa_enabled': False} → high finding."""
        resource = make_iam("alice", {"mfa_enabled": False})
        findings = checker.check_resources([resource])
        assert findings, "Expected at least one finding"
        high = [f for f in findings if f.severity == "high"]
        assert high, "Expected a high-severity finding for MFA disabled"
        mfa_findings = [f for f in findings if f.finding_type == "cloud_iam_no_mfa"]
        assert mfa_findings, "Expected a cloud_iam_no_mfa finding"

    def test_iam_mfa_enabled_no_finding(self):
        """config={'mfa_enabled': True} → 0 findings (no inactivity either)."""
        resource = make_iam("bob", {"mfa_enabled": True})
        findings = checker.check_resources([resource])
        mfa_findings = [f for f in findings if f.finding_type == "cloud_iam_no_mfa"]
        assert len(mfa_findings) == 0, "No MFA finding expected when MFA is enabled"

    def test_iam_inactive_user_is_medium(self):
        """config={'mfa_enabled': True, 'last_activity_days': 120} → medium finding."""
        resource = make_iam("carol", {"mfa_enabled": True, "last_activity_days": 120})
        findings = checker.check_resources([resource])
        inactive = [f for f in findings if f.finding_type == "cloud_iam_inactive_user"]
        assert inactive, "Expected an inactive user finding"
        assert inactive[0].severity == "medium"

    def test_mixed_resources_returns_all_findings(self):
        """1 S3 public + 1 SG open SSH + 1 MFA disabled → at least 3 findings total."""
        resources = [
            make_s3("bucket1", {"acl": "public-read-write"}),
            make_sg("sg1", {"inbound_rules": [{"cidr": "0.0.0.0/0", "port": 22, "protocol": "tcp"}]}),
            make_iam("dave", {"mfa_enabled": False}),
        ]
        findings = checker.check_resources(resources)
        assert len(findings) >= 3, f"Expected at least 3 findings, got {len(findings)}: {[f.finding_type for f in findings]}"
