web: python manage.py collectstatic --noinput && gunicorn config.wsgi:application --log-file - --workers 3 --threads 2 --timeout 200
