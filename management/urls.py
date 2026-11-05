from django.urls import path
from management import views

urlpatterns = [
    # 基础功能路由
    path('', views.index, name='homepage'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('set_password/', views.set_password, name='set_password'),

    # 社团管理路由
    path('view_club_list/', views.view_club_list, name='view_club_list'),
    path('club_detail/<int:club_id>/', views.club_detail, name='club_detail'),
    path('club/<int:club_id>/upload_images/', views.upload_club_images, name='upload_club_images'),
    path('club/image/<int:img_id>/delete/', views.delete_club_image, name='delete_club_image'),

    # 成员管理路由
    path('join_club/<int:club_id>/', views.join_club, name='join_club'),
    path('quit_club/<int:club_id>/', views.quit_club, name='quit_club'),
    path('my_clubs/', views.my_clubs, name='my_clubs'),
    path('club_members/<int:club_id>/', views.show_members, name='show_members'),
    path('delete_member/<int:membership_id>/', views.delete_member, name='delete_member'),

    # 社长管理路由
    path('club_manage/<int:club_id>/', views.club_manager_dashboard, name='club_manager'),
    path('club_manage/<int:club_id>/submit/', views.submit_activity_material, name='submit_material'),

    path('attachment/<int:attachment_id>/', views.download_attachment, name='download_attachment'),

    # 活动管理路由
    path('activity/signup/<int:activity_id>/', views.signup_activity, name='signup_activity'),
    path('activity/cancel/<int:activity_id>/', views.cancel_signup, name='cancel_signup'),
    path('activity/<int:activity_id>/', views.activity_detail, name='activity_detail'),
    path('activity_list/', views.activity_list, name='activity_list'),
]