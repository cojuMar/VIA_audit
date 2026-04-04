from dataclasses import dataclass
from typing import List, Optional
from .retriever import RetrievedChunk


SYSTEM_PROMPT = """You are an expert compliance auditor generating evidence-based audit narratives for the Aegis compliance platform.

Your role is to produce precise, factual audit narratives that:
1. Are STRICTLY grounded in the provided evidence records — never invent or infer facts not present in the evidence
2. Cite specific evidence records using their [CITATION:N] tags
3. Use professional audit language appropriate for SOC 2, ISO 27001, and PCI DSS frameworks
4. Flag any control gaps or anomalies found in the evidence
5. Are concise and structured (executive summary → findings → conclusion)

CRITICAL: Every factual claim in your narrative MUST be supported by at least one cited evidence record. If the evidence is insufficient to support a claim, explicitly state "Insufficient evidence to assess [control area]" rather than making unsupported assertions.

Do not disclose transaction amounts or financial figures — these are private inputs to zero-knowledge proofs and must not appear in audit narratives."""


@dataclass
class AuditPrompt:
    system_prompt: str
    user_prompt: str
    context_chunks: List[RetrievedChunk]
    token_estimate: int


class AuditPromptBuilder:
    """Constructs evidence-grounded prompts for Claude audit narrative generation.

    The prompt structure embeds each retrieved evidence chunk with a [CITATION:N] tag
    so that the hallucination guardrail can cross-reference claims against sources.
    """

    AVG_CHARS_PER_TOKEN = 4  # Conservative estimate for compliance text

    def build(
        self,
        framework: str,
        control_id: Optional[str],
        period_start: str,
        period_end: str,
        chunks: List[RetrievedChunk],
        max_tokens: int = 8192,
    ) -> AuditPrompt:
        """Build a complete audit prompt with embedded evidence citations.

        Args:
            framework: Compliance framework ('soc2', 'iso27001', 'pci_dss', 'custom')
            control_id: Specific control identifier (e.g. 'CC6.1')
            period_start/end: Audit period
            chunks: Retrieved evidence chunks from EvidenceRetriever
            max_tokens: Maximum context window budget

        Returns:
            AuditPrompt ready for Claude API submission.
        """
        # Build evidence context block
        evidence_lines = []
        for chunk in chunks:
            evidence_lines.append(
                f"[CITATION:{chunk.rank}] (similarity={chunk.similarity_score:.3f})\n{chunk.chunk_text}"
            )
        evidence_block = '\n\n'.join(evidence_lines)

        # Build the control specification
        control_spec = f"Control {control_id}" if control_id else "General compliance assessment"
        framework_label = {
            'soc2': 'SOC 2 Type II',
            'iso27001': 'ISO 27001:2022',
            'pci_dss': 'PCI DSS v4.0',
            'custom': 'Custom Framework',
        }.get(framework, framework.upper())

        user_prompt = f"""Generate an audit narrative for the following:

Framework: {framework_label}
Control: {control_spec}
Audit Period: {period_start} to {period_end}
Evidence Records: {len(chunks)} records retrieved

--- EVIDENCE CONTEXT ---
{evidence_block}
--- END EVIDENCE CONTEXT ---

Instructions:
- Write a structured audit narrative with: Executive Summary, Detailed Findings, and Conclusion
- Cite every factual claim using [CITATION:N] tags referencing the evidence above
- Note any control gaps, anomalies, or insufficient evidence
- Do not invent facts — if evidence is absent, state it explicitly
- Keep narrative concise (400-600 words target)"""

        token_estimate = (len(SYSTEM_PROMPT) + len(user_prompt)) // self.AVG_CHARS_PER_TOKEN

        return AuditPrompt(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            context_chunks=chunks,
            token_estimate=token_estimate,
        )
