# Generated by Django 5.0.2 on 2024-02-24 14:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0007_userbookrelation_comments'),
    ]

    operations = [
        migrations.AddField(
            model_name='book',
            name='discount',
            field=models.BooleanField(default=False),
        ),
    ]
