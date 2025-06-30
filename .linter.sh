#!/bin/bash
cd /home/kavia/workspace/code-generation/taskflow-95724-b6404a85/task_manager_backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

