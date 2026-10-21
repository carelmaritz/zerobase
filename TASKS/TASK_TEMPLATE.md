# TASK-[ID]: [Short Descriptive Title]

**Status**: [TODO|IN_PROGRESS|BLOCKED|REVIEW|DONE]
**Priority**: [C|H|M|L] - [Critical|High|Medium|Low]
**Effort**: [S|M|L|XL] - [1-2 days|3-5 days|1-2 weeks|2+ weeks]
**Assigned**: [Agent name or "Unassigned"]
**Created**: YYYY-MM-DD
**Started**: YYYY-MM-DD (when work begins)
**Completed**: YYYY-MM-DD (when work ends)
**Branch**: [branch name, e.g., TASK-C001]
**Dependencies**: [TASK-XXX, TASK-YYY or "None"]

---

## Objective

[Clear statement of what needs to be accomplished and why]

---

## Background

[Context: Why is this task needed? What problem does it solve? What is the current state?]

---

## Technical Requirements

[Specific technical requirements, constraints, or specifications]

### Success Criteria
- [ ] [Measurable criterion 1]
- [ ] [Measurable criterion 2]
- [ ] [Measurable criterion 3]

### Out of Scope

[Explicitly NOT part of this task — the tempting adjacent refactor, the related
bug, the nice-to-have. Discoveries in these areas get noted in the task file
or raised as new tasks, not silently fixed. Scope drift is the quiet killer.]

---

## Freedom

*What the assigned agent may decide alone vs. what needs sign-off.*

**Free to decide**: [e.g., naming, file layout, choice among libraries already in the project]

**Ask first**: [e.g., new dependencies, schema changes, anything touching security-sensitive code]

---

## Implementation Plan

### Phase 1: [Name]
- [ ] Step 1
- [ ] Step 2
- [ ] Step 3

### Phase 2: [Name]
- [ ] Step 1
- [ ] Step 2

*(Add more phases as needed)*

---

## Work Completed

*Fill this section when task is DONE or IN_PROGRESS*

### Files Created/Modified
- `path/to/file1.py` - Description of changes
- `path/to/file2.yaml` - Description of changes

### Key Decisions Made
- [Decision 1 and rationale]
- [Decision 2 and rationale]

### Implementation Summary
[Brief overview of approach taken]

---

## Failed Approaches

*What was tried and abandoned, and WHY. Highest-value section for anyone
(human or agent) who touches this task later — it prevents the same dead
end being rediscovered at full cost. Never delete entries; they are the
point. Write "None yet" rather than removing the section.*

- [Approach 1]: Why it was abandoned (e.g., library X doesn't support Y; approach conflicted with constraint Z)
- [Approach 2]: Why it was abandoned

---

## Testing

### Test Strategy
[How will this be tested?]

### Test Cases
- [ ] Test case 1: [Description]
- [ ] Test case 2: [Description]

### Expected Results
[What should happen when working correctly]

---

## Installation/Deployment
*Include if task requires deployment steps - otherwise mark as N/A*

**Deployment Steps**:
1. [Step 1]
2. [Step 2]

**Verification**:
- [ ] [How to verify deployment succeeded]

---

## Network Configuration
*Include if task involves inter-service communication - otherwise mark as N/A*

**Endpoints**:
- [Service A] → [Service B]: [Protocol/Port]

**Firewall Rules**:
- [Rule details if applicable]

---

## Performance Considerations
*Include for tasks with performance implications - otherwise mark as N/A*

- Expected resource usage (CPU, memory, disk)
- Latency requirements
- Scaling considerations

---

## Security Considerations
*Include for tasks with security implications - otherwise mark as N/A*

- Authentication/authorization requirements
- Data sensitivity
- Network security
- Secrets management

---

## Known Issues & Gotchas

- [ ] [Issue 1]: Description and workaround
- [ ] [Issue 2]: Description and workaround

*(Remove if none)*

---

## Rollback Plan

*How to undo this change if needed*

**Steps**:
1. [Rollback step 1]
2. [Rollback step 2]

**Validation**:
- [How to verify rollback succeeded]

---

## Next Steps

*Fill when task is complete or near completion*

- [ ] Follow-up task 1: [Description] (TASK-XXX)
- [ ] Follow-up task 2: [Description] (TASK-YYY)
- [ ] Future enhancement: [Description]

---

## Related Tasks

- **Depends On**: [TASK-XXX, TASK-YYY or "None"]
- **Blocks**: [TASK-AAA, TASK-BBB or "None"]
- **Related**: [TASK-CCC, TASK-DDD or "None"]

---

## References

- [Link to design doc]
- [Link to PR]
- [Link to external documentation]
- [Link to API docs]

*(Remove if none)*

---

## Notes

[Any additional context, learnings, or observations]

---

*Last Updated: YYYY-MM-DD by [Agent/Person Name]*

---

## Template Usage Guide

**For Small Tasks (S effort)**: Use Objective, Technical Requirements (incl. Out of Scope), Freedom, Implementation Plan, Testing, and Work Completed. Keep Failed Approaches if anything was abandoned. Mark other sections as N/A or remove.

**For Medium/Large Tasks (M/L effort)**: Use most sections as relevant to the task.

**For Critical/Complex Tasks (XL effort)**: Use all sections comprehensively.

**Always keep, never prune**: Out of Scope, Freedom, and Failed Approaches. These three are what allow an agent to work a task safely without supervision — they are cheap to fill and expensive to lack.
