#!/usr/bin/env bash

# To be run after `git clone`
# INV: Should be idempotent

# register .githooks as directory for git hooks path
git config --local core.hooksPath .githooks/ # since git 2.9
# make hooks executable
chmod +x ./.githooks/*