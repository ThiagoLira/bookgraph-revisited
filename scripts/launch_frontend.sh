#!/bin/bash
# Launch a simple HTTP server to view the frontend
echo "Starting frontend server at http://localhost:8000/frontend/"
echo "Press Ctrl+C to stop."
python3 -m http.server 8000
