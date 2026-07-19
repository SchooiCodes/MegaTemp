name: Pull request
description: Describe your changes
title: "[Type] Short summary"
labels: []
body:
  - type: markdown
    attributes:
      value: |
        Thanks for the contribution! Please fill out the template below.
  - type: textarea
    id: summary
    attributes:
      label: What does this PR do?
      description: A clear and concise description of the change.
    validations:
      required: true
  - type: textarea
    id: related
    attributes:
      label: Related issues
      description: "e.g. Fixes #42 / Closes #17"
    validations:
      required: false
  - type: textarea
    id: testing
    attributes:
      label: How was this tested?
      placeholder: "Ran `python main.py`, Ruff checks, etc."
    validations:
      required: false
  - type: checkboxes
    id: checklist
    attributes:
      label: Checklist
      options:
        - label: "I ran `ruff check .` and `ruff format .`"
        - label: "I updated documentation where needed"
        - label: "My changes are licensed under GPL-3.0"
