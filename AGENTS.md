# Agent Instructions

## General behavior

- Make small, targeted changes.
- Do not rewrite whole files unless explicitly asked.
- Do not reformat unrelated code.
- Before editing, inspect the relevant files.
- After editing, summarize changed files and verification steps.
- Prefer fixing root causes over suppressing errors.

## Safety

- Never run destructive git commands.
- Never delete data, cache folders, imagery, databases, or generated products without approval.
- Ask before installing packages or changing Docker configuration.
- Ask before running long or destructive commands.

## Python workflow

- Prefer targeted tests when available.
- Use `ruff check .` for lint checks.
- Use `pytest --collect-only` before running large test suites.
- Preserve existing public APIs unless the task explicitly requires changing them.

## HDF5 / NetCDF / xarray / h5py rules

- Ensure files, datasets, and file managers are closed.
- Prefer context managers where possible.
- If using xarray, check whether `.close()` is needed after loading or rendering.
- Avoid keeping dataset objects alive longer than necessary.
- When fixing leaks, explain which handle was leaking and where it is now closed.

# File editing rules

- When asked to create or modify files, use Kilo's file editing/write tool.
- Do not create or modify files with bash commands like `echo`, `touch`, `cat >`, `Set-Content`, `Out-File`, `sed -i`, or redirection unless explicitly asked.
- Bash may be used for inspection commands such as `git status`, `git diff`, `dir`, `ls`, and test commands.
- If the file editing tool is unavailable, say so instead of printing JSON tool calls in chat.
- Never print raw tool-call JSON as the final answer.