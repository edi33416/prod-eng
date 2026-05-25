project = "Production Systems Engineering"
copyright = "2024, Course Authors"
author = "Course Authors"

extensions = [
    "sphinx_togglebutton",
    "sphinx_copybutton",
]

copybutton_prompt_text = r"\$ |>>> "
copybutton_prompt_is_regexp = True

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
