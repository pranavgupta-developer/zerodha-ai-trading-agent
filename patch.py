import re

with open("app/main.py", "r") as f:
    content = f.read()

# Replace from 'while True:' up to 'await asyncio.sleep'
# We will use string slicing and regex carefully
