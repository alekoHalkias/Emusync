# Handoff: #683 Update React and React types to 19

## Metadata
- Issue: #683
- Branch: feature/683-react-19
- PR: none
- Status: implementing
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
Bump react, react-dom, @types/react, @types/react-dom from 18 to 19.

## 2. Design
### Scope: frontend deps; renderer only
### Plan Target: fplan
### Difficulty: 3/10 (index.tsx already uses createRoot; no forwardRef/defaultProps/propTypes found)
### Backwards Compatibility: not breaking

## 6. Testing Plan
Existing suite + tsc both configs + build-gui. No new tests.

## 12. Log
- 2026-11-01 issue/design/fplan/tplan: collapsed for a dependency-only change
