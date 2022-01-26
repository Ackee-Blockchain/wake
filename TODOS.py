# todos that don't fit anywhere else (because of the limited set of supported formats:
# https://github.com/alstr/todo-to-issue-action#supported-languages
# Using python extension here bc it has simpler comment format than markdown :D

# TODO: Fix black & pyright pre-commit hooks
#  There are two problems with our current pre-commit hooks:
#    1. `black` and `pyright` run also on files that are not being committed.
#    2. we don't immediately commit the changes that `black` makes
#   Ideally, we'll fix this soon.
#  assignees: michprev
