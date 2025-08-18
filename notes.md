•	openai = official SDK (Responses API)
•	pydantic = optional local validation
•	typer = CLI
•	numpy = log‑odds math

. Removed: venv/ directory
  2. Added:
    - pyproject.toml - Modern Python project configuration
    - uv.lock - Lockfile for reproducible builds
    - .venv/ - uv-managed virtual environment
    - main.py - Basic Python entry point
    - README.md - Project readme

Usage commands:
  - Run code: uv run python main.py
  - Add dependencies: uv add package-name
  - Install dependencies: uv sync
  - Activate shell: uv shell (optional)