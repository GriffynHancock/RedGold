---
title: Sources
question: What is every claim in this spec grounded in?
sections: [19]
spec: RedGold design
status: draft
date: 2026-08-03
---

## 19. Sources

**Benchmarks and papers**
BountyBench · CVE-Bench (arXiv 2503.17332) · CyberGym (arXiv 2506.02548) · CAIBench (arXiv
2510.24317) · CAI (arXiv 2504.06017) · EnIGMA (arXiv 2409.16165) · D-CIPHER (arXiv 2502.10931) ·
Hacking CTFs with Plain Agents (arXiv 2412.02776) · Sifting the Noise (arXiv 2601.22952) ·
QASecClaw (arXiv 2605.01885) · PentestGPT (USENIX Security 2024)

**Systems**
Google Project Naptime and Big Sleep (Project Zero, 2024) · XBOW engineering blog · OpenAI Aardvark ·
usestrix/strix · protectai/vulnhuntr · aliasrobotics/cai · 0xSteph/pentest-ai-agents ·
Stickman230/claude-pentest · frendysanusi/claude-pentest-skills · Horizon3 NodeZero · Terra Security
(CVE-2026-25724)

**Attack surface and asset discovery**
Qualys Attribution Confidence Score methodology · OWASP Amass · ProjectDiscovery alterx/subfinder/
httpx · Cloudflare shared-IP documentation · OpenEASD · syft / cdxgen · gitleaks / trufflehog ·
HackerOne scope schema via arkadiyt/bounty-targets-data · RFC 9116 · NIST OSCAL · NIST SP 800-115 ·
PTES · OWASP WSTG / ASVS / API Top 10 2023

**Incident and market data**
RedHunt Labs Project Resonance Wave 15 · CVE-2025-48757 (Lovable/Supabase) · Tea app breach
(July 2025) · PocketOS Railway volume deletion · Replit production DB deletion (July 2025) ·
McKinsey Lilli incident (Feb 2026) · Vercel Deployment Protection documentation

**Claude Code mechanics**
code.claude.com/docs/en/{hooks, memory, sub-agents, skills, plugins-reference, plugin-marketplaces,
settings, output-styles, mcp} · platform.claude.com Agent Skills best practices

**Prior work**
The prior engagement's own directory under `~/engagements/` — FRAMEWORK.md, FRAMEWORK_BUILD_PLAN.md,
research/frameworks-research.md, status.md, phase*.json, report_client.md

## Added 2026-08-04 — benchmark calibration pass

Verified against primary sources for §20:

- BountyBench — arXiv 2505.15216 (Table 1, per-agent Detect/Exploit/Patch)
- CVE-Bench — arXiv 2503.17332 (§4.2 success rates; Table 5 failure taxonomy)
- CAIBench — arXiv 2510.24317 (knowledge 70–89% vs execution 20–50%)
- PACEbench — arXiv 2510.11688 (0/7 models vs active defences)
- Frontier LLM web-app evaluation + detection FPR — arXiv 2605.23243 (Table 2)
- SAST triage filtering — arXiv 2601.22952
- Soft Self-Consistency — arXiv 2402.13212 (ACL 2024)
- OpenAI o3/o4-mini system card — deploymentsafety.openai.com

**Corrections made in this pass:** the BountyBench figures were previously presented as one
system's paired scores when they are per-agent rows; CVE-Bench is 10% zero-day / 12.5% one-day;
CAIBench knowledge tops out at 89% not 70%; the "self-consistency +0–2pp" claim had no traceable
source and was removed.

**Explicitly not cited** (could not be verified from primary text): Gemini 3 Pro FSF report figures,
Claude Opus 4.6 system card numbers reached only via secondary reporting, AutoPT (arXiv 2411.01236)
and AutoPenBench (arXiv 2410.03225) success rates, and any press claim about model performance in
government network tests.
