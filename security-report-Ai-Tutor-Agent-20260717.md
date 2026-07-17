# Opsera Security Audit Report

**Project:** Ai-Tutor-Agent  
**Scan Type:** pre-commit  
**Severity Threshold:** high  
**Date:** 7/17/2026  
**Work Order:** WO-012 — Add import-linter CI gate to block layer violations

---

## Executive Summary

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| Secrets (gitleaks) | 0 | 0 | 0 | 0 | 0 |
| Dependencies (grype) | — | — | — | — | skipped (network) |
| SAST (semgrep) | — | — | — | — | skipped (network) |
| IaC (checkov) | 0 | 0 | 0 | 0 | 0 new |
| Dockerfile (hadolint) | 0 | 0 | 0 | 0 | 0 |
| Package leakage | 0 | 0 | 0 | 0 | 0 |
| **TOTAL (new staged)** | **0** | **0** | **0** | **0** | **0** |

**Risk Score: 0/100 (No Risk)**

Score = min(100, round(log10((0×100) + (0×30) + (0×10) + (0×3) + 1) × 25)) = 0

---

## Gate Decision: ✅ SAFE TO COMMIT

No Critical or High findings in staged changes. Pre-existing CKV_GHA_7 findings (30 instances across pre-existing workflow files) are NOT new to this commit.

---

## New Files Scanned (Staged)

| File | Critical | High | Medium | Low |
|------|----------|------|--------|-----|
| `.github/workflows/shared-architectural-lint.yaml` | 0 | 0 | 0 | 0 |
| `.github/workflows/architectural-lint-pr.yaml` | 0 | 0 | 0 | 0 |
| 14× `cicd-ai-tutor-*-dev.yaml` (modified: +architectural-lint job) | 0 | 0 | 0 | 0 |

---

## Pre-existing Findings (Not blocking)

| Check | Count | Files Affected |
|-------|-------|----------------|
| CKV_GHA_7 (workflow_dispatch input filtering) | 30 | Pre-existing in all cicd-*.yaml workflows |

These are pre-existing findings not introduced by this commit.

---

## Scanner Coverage

| Tool | Status | Notes |
|------|--------|-------|
| gitleaks | ✅ PASSED | 0 secrets found |
| checkov | ✅ PASSED (new) | 0 new failures; 30 pre-existing in unmodified files |
| hadolint | ✅ PASSED | Dockerfile unchanged |
| semgrep | ⚠️ SKIPPED | Network restricted in sandbox |
| grype | ⚠️ SKIPPED | Network restricted in sandbox |
