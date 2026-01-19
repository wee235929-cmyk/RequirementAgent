# Role Templates

This folder contains Jinja2 templates for role-specific prompts used in requirements generation.

## How to Add a New Role

1. Create a new `.j2` file with the role name in snake_case (e.g., `security_analyst.j2`)
2. The role name will be automatically derived from the filename (e.g., "Security Analyst")
3. Use the following variables in your template:
   - `{{ history }}` - Conversation history
   - `{{ focus }}` - Current focus area for requirements

## Template Structure

```jinja2
{#
Role: [Role Name]
Description: [Brief description of the role]
#}
You are [role description].

Based on the following conversation history and focus {{ focus }}, [what the role should do].

History: {{ history }}

[Output guidance and standards to follow]
```

## Available Roles

- **Requirements Analyst** (`requirements_analyst.j2`) - Business analyst for requirements elicitation
- **Software Architect** (`software_architect.j2`) - System design and architecture
- **Software Developer** (`software_developer.j2`) - Implementation guidance
- **Test Engineer** (`test_engineer.j2`) - Test cases and quality assurance

## Modifying Roles

Simply edit the corresponding `.j2` file. Changes take effect immediately on the next request.

## Deleting Roles

Remove the `.j2` file. The role will no longer appear in the available roles list.
