# Implement Skill

Execute the approved plan step by step.

## Goal

Work through each step in the plan, updating the handoff file after each step.

## Rules

- One step per commit
- Update the handoff's implementation section after each step
- Append to the log after each step
- Never edit files outside of approved plans
- Push and open PRs automatically after each commit

## Actions

1. Read the handoff file to get current status
2. Determine the next unchecked step
3. Execute the step (read/write/edit files as needed)
4. Commit with message format: `#<issue> step <N>: <description>`
5. Update the handoff: mark step done, append to log
6. If all steps are done, set Status to `implemented`
7. If revision is needed, set Status back to `bplan` or `implementing`

## Output

Progress through each step. When complete, the feature branch is ready for review.
