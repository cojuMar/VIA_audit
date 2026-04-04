from collections import defaultdict
from datetime import datetime, timedelta

from rapidfuzz import fuzz

from .models import InvoiceRecord, MonitoringFinding


def _parse_date(date_str: str) -> datetime | None:
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


class InvoiceAnalyzer:
    def __init__(self, settings):
        self.fuzzy_amount_tolerance = settings.invoice_fuzzy_amount_tolerance_pct / 100
        self.fuzzy_date_window = settings.invoice_fuzzy_date_window_days
        self.split_window = settings.invoice_split_window_days

    def analyze(self, records: list[InvoiceRecord]) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []
        findings.extend(self._detect_exact_duplicates(records))
        findings.extend(self._detect_fuzzy_duplicates(records))
        findings.extend(self._detect_invoice_splitting(records))
        findings.extend(self._detect_round_amounts(records))
        return findings

    # ------------------------------------------------------------------
    # Exact duplicate detection
    # ------------------------------------------------------------------

    def _detect_exact_duplicates(self, records: list[InvoiceRecord]) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []
        # Group by (vendor_name.lower(), amount)
        groups: dict[tuple, list[InvoiceRecord]] = defaultdict(list)
        for rec in records:
            key = (rec.vendor_name.strip().lower(), rec.amount)
            groups[key].append(rec)

        reported_pairs: set[frozenset] = set()

        for (vendor_lower, amount), group in groups.items():
            if len(group) < 2:
                continue
            # Sort by date for consistent pairing
            dated = []
            for rec in group:
                d = _parse_date(rec.invoice_date)
                dated.append((d, rec))
            dated.sort(key=lambda x: (x[0] or datetime.min))

            for i in range(len(dated)):
                for j in range(i + 1, len(dated)):
                    d1, r1 = dated[i]
                    d2, r2 = dated[j]

                    if d1 and d2:
                        delta = abs((d2 - d1).days)
                        if delta > 7:
                            continue

                    pair_key = frozenset([r1.invoice_id, r2.invoice_id])
                    if pair_key in reported_pairs:
                        continue
                    reported_pairs.add(pair_key)

                    findings.append(
                        MonitoringFinding(
                            finding_type="duplicate_invoice",
                            severity="high",
                            title=f"Exact Duplicate Invoice: {r1.vendor_name} - ${amount:.2f}",
                            description=(
                                f"Invoices {r1.invoice_id} and {r2.invoice_id} from vendor "
                                f"'{r1.vendor_name}' have identical amounts (${amount:.2f}) "
                                f"within a 7-day window ({r1.invoice_date} vs {r2.invoice_date})."
                            ),
                            entity_type="invoice",
                            entity_id=r1.invoice_id,
                            entity_name=r1.vendor_name,
                            evidence={
                                "invoice_id_1": r1.invoice_id,
                                "invoice_id_2": r2.invoice_id,
                                "vendor": r1.vendor_name,
                                "amount": amount,
                                "date_1": r1.invoice_date,
                                "date_2": r2.invoice_date,
                            },
                            risk_score=7.5,
                        )
                    )

        return findings

    # ------------------------------------------------------------------
    # Fuzzy duplicate detection
    # ------------------------------------------------------------------

    def _detect_fuzzy_duplicates(self, records: list[InvoiceRecord]) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []
        reported_pairs: set[frozenset] = set()
        vendor_similarity_threshold = 85

        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                r1 = records[i]
                r2 = records[j]

                # Skip if exact same vendor (handled by exact duplicate check)
                if r1.vendor_name.strip().lower() == r2.vendor_name.strip().lower():
                    continue

                # Check vendor name similarity
                similarity = fuzz.ratio(r1.vendor_name.strip().lower(), r2.vendor_name.strip().lower())
                if similarity < vendor_similarity_threshold:
                    continue

                # Check amount within tolerance
                if r1.amount == 0 and r2.amount == 0:
                    amount_ok = True
                elif r1.amount == 0 or r2.amount == 0:
                    amount_ok = False
                else:
                    pct_diff = abs(r1.amount - r2.amount) / max(abs(r1.amount), abs(r2.amount))
                    amount_ok = pct_diff <= self.fuzzy_amount_tolerance
                if not amount_ok:
                    continue

                # Check date window
                d1 = _parse_date(r1.invoice_date)
                d2 = _parse_date(r2.invoice_date)
                if d1 and d2:
                    if abs((d2 - d1).days) > self.fuzzy_date_window:
                        continue

                pair_key = frozenset([r1.invoice_id, r2.invoice_id])
                if pair_key in reported_pairs:
                    continue
                reported_pairs.add(pair_key)

                mid_amount = (r1.amount + r2.amount) / 2
                findings.append(
                    MonitoringFinding(
                        finding_type="near_duplicate_invoice",
                        severity="medium",
                        title=f"Near-Duplicate Invoice: {r1.vendor_name} ~${mid_amount:.2f}",
                        description=(
                            f"Invoices {r1.invoice_id} ('{r1.vendor_name}', ${r1.amount:.2f}) and "
                            f"{r2.invoice_id} ('{r2.vendor_name}', ${r2.amount:.2f}) appear to be "
                            f"near-duplicates (vendor similarity: {similarity}%, amounts within tolerance)."
                        ),
                        entity_type="invoice",
                        entity_id=r1.invoice_id,
                        entity_name=r1.vendor_name,
                        evidence={
                            "invoice_id_1": r1.invoice_id,
                            "invoice_id_2": r2.invoice_id,
                            "vendor_1": r1.vendor_name,
                            "vendor_2": r2.vendor_name,
                            "vendor_similarity_pct": similarity,
                            "amount_1": r1.amount,
                            "amount_2": r2.amount,
                            "date_1": r1.invoice_date,
                            "date_2": r2.invoice_date,
                        },
                        risk_score=5.5,
                    )
                )

        return findings

    # ------------------------------------------------------------------
    # Invoice splitting detection
    # ------------------------------------------------------------------

    def _detect_invoice_splitting(self, records: list[InvoiceRecord]) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []

        # Group by vendor
        vendor_records: dict[str, list[InvoiceRecord]] = defaultdict(list)
        for rec in records:
            vendor_records[rec.vendor_name.strip().lower()].append(rec)

        for vendor_lower, group in vendor_records.items():
            if len(group) < 3:
                continue

            # Sort by date
            dated: list[tuple[datetime | None, InvoiceRecord]] = []
            for rec in group:
                d = _parse_date(rec.invoice_date)
                dated.append((d, rec))
            dated.sort(key=lambda x: (x[0] or datetime.min))

            # Sliding window: find clusters of 3+ invoices within split_window days
            reported_clusters: set[frozenset] = set()
            for start_idx in range(len(dated)):
                d_start, r_start = dated[start_idx]
                if d_start is None:
                    continue

                window_end = d_start + timedelta(days=self.split_window)
                cluster: list[tuple[datetime | None, InvoiceRecord]] = []
                for k in range(start_idx, len(dated)):
                    dk, rk = dated[k]
                    if dk is None or dk > window_end:
                        break
                    cluster.append((dk, rk))

                if len(cluster) < 3:
                    continue

                cluster_key = frozenset(r.invoice_id for _, r in cluster)
                if cluster_key in reported_clusters:
                    continue

                # Check approval threshold logic
                threshold = cluster[0][1].approval_threshold
                individual_amounts = [r.amount for _, r in cluster]
                total = sum(individual_amounts)

                if threshold is not None:
                    # Flag if individual invoices are below threshold but total exceeds it
                    all_below = all(a < threshold for a in individual_amounts)
                    if not (all_below and total > threshold):
                        continue

                reported_clusters.add(cluster_key)
                invoice_ids = [r.invoice_id for _, r in cluster]
                vendor_display = cluster[0][1].vendor_name

                findings.append(
                    MonitoringFinding(
                        finding_type="invoice_splitting",
                        severity="high",
                        title=f"Possible Invoice Splitting: {vendor_display} - ${total:.2f} total",
                        description=(
                            f"{len(cluster)} invoices to '{vendor_display}' totalling ${total:.2f} "
                            f"within {self.split_window} days. Individual amounts are below the "
                            f"approval threshold (${threshold:.2f}) but combined total exceeds it."
                            if threshold
                            else f"{len(cluster)} invoices to '{vendor_display}' totalling ${total:.2f} "
                            f"within {self.split_window} days."
                        ),
                        entity_type="vendor",
                        entity_id=None,
                        entity_name=vendor_display,
                        evidence={
                            "vendor": vendor_display,
                            "invoice_ids": invoice_ids,
                            "individual_amounts": individual_amounts,
                            "total_amount": round(total, 2),
                            "threshold": threshold,
                            "window_days": self.split_window,
                            "invoice_count": len(cluster),
                        },
                        risk_score=7.5,
                    )
                )

        return findings

    # ------------------------------------------------------------------
    # Round amount detection
    # ------------------------------------------------------------------

    def _detect_round_amounts(self, records: list[InvoiceRecord]) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []
        for rec in records:
            if rec.amount <= 1000:
                continue
            for divisor in [1000, 500, 100]:
                if rec.amount % divisor == 0:
                    findings.append(
                        MonitoringFinding(
                            finding_type="round_amount_invoice",
                            severity="low",
                            title=f"Round Amount Invoice: {rec.vendor_name} - ${rec.amount:.2f}",
                            description=(
                                f"Invoice {rec.invoice_id} from '{rec.vendor_name}' has a suspiciously "
                                f"round amount of ${rec.amount:.2f} (exact multiple of ${divisor})."
                            ),
                            entity_type="invoice",
                            entity_id=rec.invoice_id,
                            entity_name=rec.vendor_name,
                            evidence={
                                "amount": rec.amount,
                                "divisor": divisor,
                                "invoice_date": rec.invoice_date,
                            },
                            risk_score=2.0,
                        )
                    )
                    break  # Report only the largest matching divisor

        return findings
