from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from dotenv import load_dotenv

# load_dotenv("/home/ubuntu/abepte/ABE-PTE-BACKEND/.env")
os.environ.setdefault('DJANGO_SETTINGS_MODULE','abe_pte.settings')
app = Celery('abe_pte')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
