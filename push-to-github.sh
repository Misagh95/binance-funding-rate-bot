#!/bin/bash
set -e

REPO_URL="$1"
if [ -z "$REPO_URL" ]; then
  echo "Usage: ./push-to-github.sh https://github.com/YOUR_USERNAME/REPO_NAME.git"
  exit 1
fi

git init
git add .
git commit -m "Initial commit" || true
git remote remove origin 2>/dev/null || true
git remote add origin "$REPO_URL"
git branch -M main
git push -u origin main
