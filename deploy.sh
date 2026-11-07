#!/usr/bin/env bash
# Build the pygame app to WebAssembly and deploy the static output to Vercel.
set -euo pipefail
cd "$(dirname "$0")"

python3 -m pip install pygbag==0.9.3   # pinned: the version the web build was verified with
python3 -m pygbag --build --app_name eye_within_words --title "Eye Within Words" .   # outputs build/web/

# first time: `npx vercel login`, then this links/creates the project
npx vercel deploy build/web --prod
