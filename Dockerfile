# Static HTML server for this repo (timetable exports)
# Usage:
#   docker build -t hansung-info-static .
#   docker run --rm -p 8080:80 hansung-info-static
#
# Serves ./static as the web root. (We intentionally do NOT use ./docs to avoid GitHub Pages coupling.)
# Put generated HTML under static/ (e.g. static/index.html), or mount a volume at /usr/share/nginx/html.

FROM nginx:alpine

# Basic hardening / predictable behavior
RUN rm -rf /usr/share/nginx/html/*

COPY static/ /usr/share/nginx/html/

# Optional: custom nginx config (cache disabled for rapid iteration)
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
