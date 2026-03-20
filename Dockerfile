# Static HTML server for this repo (timetable exports)
# Usage:
#   docker build -t hansung-info-static .
#   docker run --rm -p 8080:80 hansung-info-static
#
# Serves ./docs as the web root. Put generated HTML under docs/ (e.g. docs/timetable.html).

FROM nginx:alpine

# Basic hardening / predictable behavior
RUN rm -rf /usr/share/nginx/html/*

COPY docs/ /usr/share/nginx/html/

# Optional: custom nginx config (cache disabled for rapid iteration)
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
