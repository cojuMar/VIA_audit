from .models import CloudResourceConfig, MonitoringFinding


class CloudConfigChecker:
    def check_resources(self, resources: list[CloudResourceConfig]) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []
        for resource in resources:
            if resource.resource_type == "s3_bucket":
                findings.extend(self._check_s3_bucket(resource))
            elif resource.resource_type == "security_group":
                findings.extend(self._check_security_group(resource))
            elif resource.resource_type == "iam_user":
                findings.extend(self._check_iam_user(resource))
            elif resource.resource_type in ("storage_bucket", "gcs_bucket"):
                findings.extend(self._check_storage_bucket(resource))
        return findings

    # ------------------------------------------------------------------
    # S3 bucket checks
    # ------------------------------------------------------------------

    def _check_s3_bucket(self, resource: CloudResourceConfig) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []
        cfg = resource.config
        name = resource.resource_name or resource.resource_id

        # Public access block not enabled
        pab = cfg.get("public_access_block", {})
        block_public_acls = pab.get("block_public_acls", True)
        if block_public_acls is False:
            findings.append(
                MonitoringFinding(
                    finding_type="cloud_s3_public_access",
                    severity="high",
                    title=f"S3 Bucket Public ACLs Not Blocked: {name}",
                    description=(
                        f"S3 bucket '{name}' has block_public_acls disabled, "
                        "allowing public ACL grants."
                    ),
                    entity_type="cloud_resource",
                    entity_id=resource.resource_id,
                    entity_name=resource.resource_name,
                    evidence={
                        "provider": resource.provider,
                        "region": resource.region,
                        "public_access_block": pab,
                        "check": "block_public_acls",
                    },
                    risk_score=8.0,
                )
            )

        # Public ACL on the bucket itself
        acl = cfg.get("acl", "private")
        if acl == "public-read-write":
            findings.append(
                MonitoringFinding(
                    finding_type="cloud_s3_public_access",
                    severity="critical",
                    title=f"S3 Bucket Publicly Writable: {name}",
                    description=(
                        f"S3 bucket '{name}' has ACL set to 'public-read-write', "
                        "allowing anyone on the internet to read AND write to this bucket."
                    ),
                    entity_type="cloud_resource",
                    entity_id=resource.resource_id,
                    entity_name=resource.resource_name,
                    evidence={
                        "provider": resource.provider,
                        "region": resource.region,
                        "acl": acl,
                        "check": "acl_public_read_write",
                    },
                    risk_score=10.0,
                )
            )
        elif acl == "public-read":
            findings.append(
                MonitoringFinding(
                    finding_type="cloud_s3_public_access",
                    severity="high",
                    title=f"S3 Bucket Publicly Readable: {name}",
                    description=(
                        f"S3 bucket '{name}' has ACL set to 'public-read', "
                        "allowing anyone on the internet to read its contents."
                    ),
                    entity_type="cloud_resource",
                    entity_id=resource.resource_id,
                    entity_name=resource.resource_name,
                    evidence={
                        "provider": resource.provider,
                        "region": resource.region,
                        "acl": acl,
                        "check": "acl_public_read",
                    },
                    risk_score=8.0,
                )
            )

        return findings

    # ------------------------------------------------------------------
    # Security group checks
    # ------------------------------------------------------------------

    def _check_security_group(self, resource: CloudResourceConfig) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []
        cfg = resource.config
        name = resource.resource_name or resource.resource_id
        inbound_rules = cfg.get("inbound_rules", [])

        for rule in inbound_rules:
            cidr = rule.get("cidr", "")
            port = rule.get("port")
            protocol = rule.get("protocol", "tcp")

            if cidr != "0.0.0.0/0":
                continue
            if port in (80, 443):
                continue

            if port in (22, 3389):
                severity = "critical"
                risk_score = 10.0
                port_name = "SSH (22)" if port == 22 else "RDP (3389)"
                title = f"Critical Port {port_name} Open to Internet: {name}"
                description = (
                    f"Security group '{name}' allows inbound {protocol.upper()} traffic "
                    f"on port {port} from 0.0.0.0/0 (entire internet). "
                    f"This exposes {port_name} to brute-force and remote exploitation attacks."
                )
            else:
                severity = "high"
                risk_score = 8.0
                title = f"Unrestricted Inbound Port {port} Open to Internet: {name}"
                description = (
                    f"Security group '{name}' allows inbound {protocol.upper()} traffic "
                    f"on port {port} from 0.0.0.0/0 (entire internet)."
                )

            findings.append(
                MonitoringFinding(
                    finding_type="cloud_security_group_open",
                    severity=severity,
                    title=title,
                    description=description,
                    entity_type="cloud_resource",
                    entity_id=resource.resource_id,
                    entity_name=resource.resource_name,
                    evidence={
                        "provider": resource.provider,
                        "region": resource.region,
                        "port": port,
                        "protocol": protocol,
                        "cidr": cidr,
                        "rule": rule,
                    },
                    risk_score=risk_score,
                )
            )

        return findings

    # ------------------------------------------------------------------
    # IAM user checks
    # ------------------------------------------------------------------

    def _check_iam_user(self, resource: CloudResourceConfig) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []
        cfg = resource.config
        name = resource.resource_name or resource.resource_id

        mfa_enabled = cfg.get("mfa_enabled", True)
        if mfa_enabled is False:
            findings.append(
                MonitoringFinding(
                    finding_type="cloud_iam_no_mfa",
                    severity="high",
                    title=f"IAM User Without MFA: {name}",
                    description=(
                        f"IAM user '{name}' does not have multi-factor authentication enabled. "
                        "MFA significantly reduces the risk of account compromise."
                    ),
                    entity_type="cloud_resource",
                    entity_id=resource.resource_id,
                    entity_name=resource.resource_name,
                    evidence={
                        "provider": resource.provider,
                        "region": resource.region,
                        "mfa_enabled": False,
                        "check": "mfa_enabled",
                    },
                    risk_score=8.0,
                )
            )

        last_activity_days = cfg.get("last_activity_days")
        if isinstance(last_activity_days, (int, float)) and last_activity_days > 90:
            findings.append(
                MonitoringFinding(
                    finding_type="cloud_iam_inactive_user",
                    severity="medium",
                    title=f"Inactive IAM User: {name} ({int(last_activity_days)} days)",
                    description=(
                        f"IAM user '{name}' has not been active for {int(last_activity_days)} days. "
                        "Inactive accounts should be reviewed and disabled to reduce attack surface."
                    ),
                    entity_type="cloud_resource",
                    entity_id=resource.resource_id,
                    entity_name=resource.resource_name,
                    evidence={
                        "provider": resource.provider,
                        "region": resource.region,
                        "last_activity_days": last_activity_days,
                        "check": "last_activity_days",
                    },
                    risk_score=5.5,
                )
            )

        return findings

    # ------------------------------------------------------------------
    # GCS / Storage bucket checks
    # ------------------------------------------------------------------

    def _check_storage_bucket(self, resource: CloudResourceConfig) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []
        cfg = resource.config
        name = resource.resource_name or resource.resource_id

        uniform_access = cfg.get("uniform_bucket_level_access", True)
        if uniform_access is False:
            findings.append(
                MonitoringFinding(
                    finding_type="cloud_storage_bucket_access",
                    severity="high",
                    title=f"Storage Bucket Lacks Uniform Access Control: {name}",
                    description=(
                        f"Storage bucket '{name}' does not have uniform bucket-level access enabled. "
                        "Object-level ACLs may bypass bucket-level IAM policies."
                    ),
                    entity_type="cloud_resource",
                    entity_id=resource.resource_id,
                    entity_name=resource.resource_name,
                    evidence={
                        "provider": resource.provider,
                        "region": resource.region,
                        "uniform_bucket_level_access": False,
                        "check": "uniform_bucket_level_access",
                    },
                    risk_score=7.5,
                )
            )

        public_access = cfg.get("public_access", False)
        if public_access is True:
            findings.append(
                MonitoringFinding(
                    finding_type="cloud_storage_bucket_public",
                    severity="high",
                    title=f"Storage Bucket Is Publicly Accessible: {name}",
                    description=(
                        f"Storage bucket '{name}' is configured for public access, "
                        "allowing unauthenticated users to access its contents."
                    ),
                    entity_type="cloud_resource",
                    entity_id=resource.resource_id,
                    entity_name=resource.resource_name,
                    evidence={
                        "provider": resource.provider,
                        "region": resource.region,
                        "public_access": True,
                        "check": "public_access",
                    },
                    risk_score=8.0,
                )
            )

        return findings
