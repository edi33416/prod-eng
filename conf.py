project = "Production Systems Engineering"
copyright = "2024, Course Authors"
author = "Course Authors"

extensions = [
    "sphinx_togglebutton",
]

templates_path = ["_templates"]

# Don't scan support/ directories — they contain Python source, not RST.
exclude_patterns = [
    "build",
    "_build",
    ".DS_Store",
    ".venv",
    "chapters/*/support",
]

html_theme = "furo"

html_static_path = []
