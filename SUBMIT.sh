#!/usr/bin/env bash

# LinkPlease API Submission Script
# Endpoint: https://pseudogram-api.onrender.com/v1/submit

curl -X POST https://pseudogram-api.onrender.com/v1/submit \
  -H "Content-Type: application/json" \
  -d '{
    "email": "",
    "github_repo": "https://github.com/pavan-545/Instagram-Auto-DM-Automation",
    "working_url": "",
    "loom_url": "",
    "parts_completed": "A+B+C",
    "start_date": ""
  }'
