from django.contrib import admin
from django.urls import include, path, re_path
from django.conf import settings
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('management.urls')),
]

# 申请附件通过带权限的下载视图访问，不将 activity_docs 暴露为静态目录。
if settings.DEBUG:
    urlpatterns += [re_path(
        r'^media/(?P<path>(?:club_photos|activity_gallery)/.*)$',
        serve, {'document_root': settings.MEDIA_ROOT},
    )]
