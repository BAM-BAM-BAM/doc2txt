#!/bin/bash

# Install FGT git hooks
# Run this script after cloning the repository

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Installing FGT git hooks..."

# Configure git to use .githooks directory
git -C "$REPO_ROOT" config core.hooksPath .githooks

# Make hooks executable
chmod +x "$REPO_ROOT/.githooks/"*

echo "Git hooks installed successfully"
echo "Hooks directory: $REPO_ROOT/.githooks"
