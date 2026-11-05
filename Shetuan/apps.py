from django.apps import AppConfig


class SimpleUIConfig(AppConfig):
    """保留 SimpleUI 模板，同时保留 Django 的防点击劫持中间件。"""
    name = 'simpleui'
