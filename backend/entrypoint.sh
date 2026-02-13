#!/bin/sh
set -e

python manage.py shell -c "from django.db import connection; c=connection.cursor(); c.execute('CREATE EXTENSION IF NOT EXISTS vector'); print('pgvector ready')"
python manage.py migrate
python manage.py preload_pdf

exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 120
