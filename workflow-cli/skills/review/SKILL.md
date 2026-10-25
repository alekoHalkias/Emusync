# Review Skill

Review the implemented changes from multiple dimensions.

## Goal

Review the code changes for:
- Correctness (bugs, logic errors)
- Performance (efficiency, scalability)
- Security (vulnerabilities, auth issues)
- Test coverage (missing tests)
- Documentation (updates needed)

## Actions

1. Read the handoff file and plan
2. Review the diff: `git diff main...feature/<N>-*`
3. Read key changed files for context
4. Write findings in the handoff's Review section
5. If issues found, set Status to `implementing` with revision feedback
6. If clean, set Status to `review` and request ship approval

## Output

Review findings in handoff Section 9.
