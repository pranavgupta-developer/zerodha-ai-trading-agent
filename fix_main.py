import re

with open("app/main.py", "r") as f:
    content = f.read()

# We need to wrap the body of the `for sym, result in zip(symbols, results):` loop in a try-except.
# Find the start of the loop
start_marker = "            for sym, result in zip(symbols, results):"
parts = content.split(start_marker)

# Replace the inner loop body to be surrounded by try-except
inner_code = parts[1].split("            # Broadcast market update")[0]

new_inner_code = ""
for line in inner_code.split('\n'):
    if line.strip() == "":
        new_inner_code += line + "\n"
        continue
    # Indent by 4 spaces and put it inside a try block
    if "if isinstance(result, Exception):" in line:
        new_inner_code += """
                try:
"""
    if line.startswith("                "): # Indent further
        new_inner_code += "    " + line + "\n"
    else:
        new_inner_code += line + "\n"

new_inner_code += """
                except Exception as e:
                    logger.error(f"Error processing symbol {sym}: {e}")
                    continue
"""

content = parts[0] + start_marker + new_inner_code + "            # Broadcast market update" + parts[1].split("            # Broadcast market update")[1]

with open("app/main.py", "w") as f:
    f.write(content)
