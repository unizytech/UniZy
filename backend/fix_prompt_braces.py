#!/usr/bin/env python3
"""
Fix user prompts by escaping JSON braces for Python's .format() method.

The issue: User prompts contain JSON structure examples with braces { and }.
When Python's .format(transcript=transcript) is called, it treats these as placeholders.

Solution: Double all braces except {transcript} placeholder: { → {{ and } → }}
"""

import re

def escape_prompt_braces(content: str) -> str:
    """
    Escape all braces in prompt except {transcript} placeholder.

    Strategy:
    1. Replace all { with {{
    2. Replace all } with }}
    3. Restore {transcript} placeholder by replacing {{transcript}} back to {transcript}
    """
    # Step 1 & 2: Double all braces
    escaped = content.replace('{', '{{').replace('}', '}}')

    # Step 3: Restore {transcript} placeholder
    escaped = escaped.replace('{{transcript}}', '{transcript}')

    return escaped

def fix_file(filepath: str):
    """Fix a single prompt file."""
    print(f"Processing: {filepath}")

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find USER_PROMPT definition
    # Pattern: SOME_USER_PROMPT = """..."""
    pattern = r'(.*_USER_PROMPT\s*=\s*""")(.*?)(""")'

    def replace_prompt(match):
        prefix = match.group(1)
        prompt_content = match.group(2)
        suffix = match.group(3)

        # Escape braces in prompt content
        fixed_content = escape_prompt_braces(prompt_content)

        return prefix + fixed_content + suffix

    # Replace all USER_PROMPT definitions
    fixed_content = re.sub(pattern, replace_prompt, content, flags=re.DOTALL)

    # Write back
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(fixed_content)

    print(f"✅ Fixed: {filepath}")

if __name__ == "__main__":
    files_to_fix = [
        'services/ophthal_prompt.py',
        'services/ophthal_consult_prompt.py',
        'services/ophthal_discharge_prompt.py',
        'services/optometrist_prompt.py',
    ]

    for filepath in files_to_fix:
        fix_file(filepath)

    print("\n✅ All files fixed! Braces in JSON examples are now escaped.")
