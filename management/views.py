from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, IntegrityError, DatabaseError
from django.http import FileResponse, Http404
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404

from .models import Student, Club, ClubMember, ClubActivity, ActivityGallery, ActivitySignup, ClubGallery, \
    ActivityAttachment
from .forms import SignupForm, PasswordChangeForm, ActivityForm
from .validators import validate_uploads

logger = logging.getLogger(__name__)


def is_president(user):
    return user.is_authenticated and Club.objects.filter(president=user).exists()



# --- 1. 首页视图 ---
def index(request):
    """
    系统首页视图
    参数：
    - request: HTTP请求对象
    返回值：
    - 渲染的首页模板，包含系统统计数据
    业务逻辑：
    1. 统计社团总数、学生总数和已通过审批的活动总数
    2. 渲染首页模板，传递统计数据和菜单状态
    """
    context = {
        'active_menu': 'homepage',  # 激活首页菜单
        'club_count': Club.objects.count(),  # 社团总数
        'student_count': Student.objects.count(),  # 学生总数
        # 修改点：添加 filter(status=2) 只统计已通过的活动
        'activity_count': ClubActivity.objects.filter(status=2).count(),
    }
    return render(request, 'management/index.html', context)

# --- 2. 用户注册视图 ---
def signup(request):
    if request.user.is_authenticated:
        return redirect('homepage')
    form = SignupForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            form.add_error(None, '学号或邮箱已注册，请检查后重试。')
        else:
            messages.success(request, '注册成功，请登录。')
            return redirect('login')
    return render(request, 'management/signup.html', {'form': form})



# --- 3. 用户登录视图 ---
def login_view(request):
    """
    用户登录视图
    参数：
    - request: HTTP请求对象
    返回值：
    - GET请求：渲染登录表单页面
    - POST请求：处理登录逻辑，成功后重定向到首页，失败则返回登录页
    业务逻辑：
    1. 检查用户是否已登录，已登录则重定向到首页
    2. 处理POST请求：
       - 获取表单数据
       - 使用Django认证系统验证用户
       - 验证成功则登录用户并重定向到首页
       - 验证失败则显示错误信息
    """
    if request.user.is_authenticated:
        return redirect('homepage')

    if request.method == 'POST':
        sid = request.POST.get('student_id')  # 学号
        pwd = request.POST.get('password')  # 密码

        # 验证用户身份
        user = authenticate(request, username=sid, password=pwd)
        if user is not None:
            auth_login(request, user)  # 登录用户
            return redirect('homepage')
        else:
            messages.error(request, "学号或密码错误")

    return render(request, 'management/login.html')


# --- 4. 用户注销视图 ---
@require_POST
def logout_view(request):
    auth_logout(request)
    return redirect('homepage')



# --- 5. 修改密码视图 ---
@login_required
def set_password(request):
    form = PasswordChangeForm(request.user, request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        request.user.set_password(form.cleaned_data['new_password'])
        request.user.save(update_fields=['password'])
        update_session_auth_hash(request, request.user)
        messages.success(request, '密码修改成功。')
        return redirect('set_password')
    return render(request, 'management/set_password.html', {'form': form})



# --- 6. 社团列表视图 ---
def view_club_list(request):
    """
    社团列表视图，支持分类筛选和搜索
    业务逻辑：
    1. 获取分类筛选和搜索关键词参数
    2. 查询社团数据，支持按分类筛选和名称搜索
    3. 清洗并去重社团分类，供侧边栏展示
    4. 对查询结果进行分页处理
    """
    query_category = request.GET.get('category', 'all')  # 分类筛选，默认为'all'
    keyword = request.GET.get('keyword', '')  # 搜索关键词，默认为空

    clubs = Club.objects.all().order_by('-establish_date')

    if query_category != 'all':
        clubs = clubs.filter(category=query_category)

    if keyword:
        # 同时匹配名称或描述
        clubs = clubs.filter(
            Q(name__icontains=keyword) | Q(detail__icontains=keyword)
        )

    raw_categories = Club.objects.values_list('category', flat=True).distinct()

    clean_categories = set()
    for cat in raw_categories:
        if cat and cat.strip():
            clean_categories.add(cat.strip())

    category_list = [(cat, cat) for cat in sorted(list(clean_categories))]

    paginator = Paginator(clubs, 6)
    page_number = request.GET.get('page')  # 获取当前页码
    club_list = paginator.get_page(page_number)  # 安全获取分页对象

    context = {
        'club_list': club_list,  # 分页后的社团对象集合
        'category_list': category_list,  # 去重后的分类列表
        'query_category': query_category,  # 当前选中的分类
        'keyword': keyword,  # 保持搜索框的关键词
    }
    return render(request, 'management/view_club_list.html', context)

# --- 7. 加入社团视图 ---
@login_required
@require_POST
def join_club(request, club_id):
    club = get_object_or_404(Club, pk=club_id)
    try:
        with transaction.atomic():
            Student.objects.select_for_update().get(pk=request.user.pk)
            Club.objects.select_for_update().get(pk=club.pk)
            if ClubMember.objects.filter(student=request.user, club=club).exists():
                messages.info(request, '您已经是该社团成员。')
            else:
                ClubMember.objects.create(student=request.user, club=club)
                messages.success(request, f'已加入 {club.name}。')
    except ValidationError as exc:
        messages.error(request, '；'.join(exc.messages))
    except IntegrityError:
        messages.info(request, '成员信息已更新，请刷新页面。')
    return redirect('club_detail', club_id=club_id)



@login_required
@require_POST
def quit_club(request, club_id):
    club = get_object_or_404(Club, pk=club_id)
    try:
        with transaction.atomic():
            Student.objects.select_for_update().get(pk=request.user.pk)
            Club.objects.select_for_update().get(pk=club.pk)
            member = ClubMember.objects.filter(student=request.user, club=club).first()
            if not member:
                messages.info(request, '您不是该社团成员。')
            else:
                member.delete()
                messages.success(request, f'已退出 {club.name}，该社团的活动报名已取消。')
    except ValidationError as exc:
        messages.error(request, '；'.join(exc.messages))
    return redirect('my_clubs')


@login_required
def my_clubs(request):
    """
    查看当前用户加入的所有社团视图
    参数：
    - request: HTTP请求对象
    返回值：
    - 渲染我的社团列表页面
    业务逻辑：
    1. 检查用户是否已登录（通过login_required装饰器）
    2. 查询当前用户加入的所有社团成员关系
    3. 使用select_related优化数据库查询
    4. 渲染我的社团列表页面
    """
    # 查询当前用户的所有社团成员关系，预加载社团信息
    my_memberships = ClubMember.objects.filter(student=request.user).select_related('club')
    return render(request, 'management/my_clubs.html', {'memberships': my_memberships})

# --- 9. 社团详情视图 ---
def club_detail(request, club_id):
    """
    社团详情视图
    参数：
    - request: HTTP请求对象
    - club_id: 社团ID
    返回值：
    - 渲染社团详情页面，包含社团信息、宣传照片和活动列表
    业务逻辑：
    1. 获取社团对象，不存在则返回404
    2. 查询社团的所有宣传照片
    3. 查询社团已通过审批的活动
    4. 如果用户已登录：
       - 检查用户是否是该社团成员
       - 获取用户在该社团活动中的报名记录
    5. 渲染社团详情页面
    """
    club = get_object_or_404(Club, id=club_id)

    # 查询该社团的所有宣传照片，用于前端轮播图展示
    club_images = ClubGallery.objects.filter(club=club).order_by('-upload_date')

    # 查询该社团已通过审批的活动（status=2）
    activities = ClubActivity.objects.filter(club=club, status=2).order_by('-start_time')

    is_member = False
    my_signups = []

    if request.user.is_authenticated:
        # 检查当前用户是否是该社团成员
        is_member = ClubMember.objects.filter(student=request.user, club=club).exists()

        # 获取当前用户在该社团所有活动中的报名记录
        my_signups = ActivitySignup.objects.filter(
            student=request.user,
            activity__club=club
        ).values_list('activity_id', flat=True)

    context = {
        'club': club,
        'club_images': club_images,
        'is_member': is_member,
        'activities': activities,
        'my_signups': my_signups
    }
    return render(request, 'management/club_detail.html', context)


# --- 10. 查看社团成员视图 ---
@login_required
def show_members(request, club_id):
    club = get_object_or_404(Club, pk=club_id)
    if not (request.user.is_staff or club.president_id == request.user.pk or
            ClubMember.objects.filter(student=request.user, club=club).exists()):
        raise PermissionDenied('仅社团成员及管理员可以查看名单。')
    members = ClubMember.objects.filter(club=club).select_related('student', 'club').select_related('student', 'club')
    return render(request, 'management/show_members.html', {'users': members, 'club': club})



# --- 11. 删除社团成员视图 ---
@login_required
@require_POST
def delete_member(request, membership_id):
    membership = get_object_or_404(ClubMember, pk=membership_id)
    club_id = membership.club_id
    try:
        with transaction.atomic():
            Student.objects.select_for_update().get(pk=membership.student_id)
            club = Club.objects.select_for_update().get(pk=club_id)
            if club.president_id != request.user.pk and not request.user.is_staff:
                raise PermissionDenied('仅社长及管理员可以移除成员。')
            ClubMember.objects.filter(pk=membership_id).delete()
            messages.success(request, '已移除成员并取消其社团活动报名。')
    except ValidationError as exc:
        messages.error(request, '；'.join(exc.messages))
    return redirect('club_manager', club_id=club_id)



# --- 12. 社长管理面板视图 ---
@login_required
def club_manager_dashboard(request, club_id):
    """
    社长管理面板视图
    参数：
    - request: HTTP请求对象
    - club_id: 社团ID
    返回值：
    - 渲染社长管理面板页面，包含社团管理功能
    业务逻辑：
    1. 检查用户是否已登录（通过login_required装饰器）
    2. 获取社团对象，不存在则返回404
    3. 检查用户是否是该社团的社长
    4. 查询社团的宣传照片、成员和活动记录
    5. 渲染管理面板页面
    """
    # 获取社团对象
    club = get_object_or_404(Club, id=club_id)
    # 检查当前用户是否是该社团的社长
    if club.president_id != request.user.pk and not request.user.is_staff:
        raise PermissionDenied('您没有权限管理此社团。')

    # 获取该社团的所有宣传照片
    club_images = ClubGallery.objects.filter(club=club).order_by('-upload_date')

    # 获取所有成员
    members = ClubMember.objects.filter(club=club).select_related('student', 'club')
    # 获取该社团的所有活动记录
    activities = ClubActivity.objects.filter(club=club).order_by('-start_time')

    return render(request, 'management/club_manager.html', {
        'club': club,
        'club_images': club_images,
        'members': members,
        'activities': activities
    })

# --- 13. 提交活动申请视图 ---
@login_required
@require_POST
def submit_activity_material(request, club_id):
    club = get_object_or_404(Club, pk=club_id)
    if club.president_id != request.user.pk and not request.user.is_staff:
        raise PermissionDenied('仅社长及管理员可以提交申请。')
    form = ActivityForm(request.POST)
    images, documents = request.FILES.getlist('images'), request.FILES.getlist('annex')
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect('club_manager', club_id=club_id)
    stored = []
    try:
        validate_uploads(images, documents)
        with transaction.atomic():
            club = Club.objects.select_for_update().get(pk=club_id)
            if club.president_id != request.user.pk and not request.user.is_staff:
                raise PermissionDenied('社长已变更，请刷新页面。')
            activity = form.save(commit=False)
            activity.club = club
            activity.status = 1
            activity.save()
            for file in documents:
                _save_upload(ActivityAttachment(activity=activity), 'file', file, stored)
            for image in images:
                _save_upload(ActivityGallery(activity=activity), 'image', image, stored)
        messages.success(request, '活动申请已提交，等待管理员审核。')
    except ValidationError as exc:
        _cleanup_uploads(stored)
        messages.error(request, '；'.join(exc.messages))
    except PermissionDenied:
        _cleanup_uploads(stored)
        raise
    except Exception:
        _cleanup_uploads(stored)
        logger.exception('活动提交失败')
        messages.error(request, '活动提交失败，请检查文件及活动信息后重试。')
    return redirect('club_manager', club_id=club_id)



@login_required
@require_POST
def signup_activity(request, activity_id):
    activity = get_object_or_404(ClubActivity, pk=activity_id)
    try:
        ActivitySignup.objects.create(student=request.user, activity=activity)
        messages.success(request, '活动报名成功。')
    except ValidationError as exc:
        messages.error(request, '；'.join(exc.messages))
    except IntegrityError:
        messages.info(request, '您已经报名过该活动。')
    return redirect('activity_detail', activity_id=activity_id)




@login_required
@require_POST
def cancel_signup(request, activity_id):
    activity = get_object_or_404(ClubActivity, pk=activity_id)
    with transaction.atomic():
        Student.objects.select_for_update().get(pk=request.user.pk)
        Club.objects.select_for_update().get(pk=activity.club_id)
        ClubActivity.objects.select_for_update().get(pk=activity_id)
        ActivitySignup.objects.filter(student=request.user, activity_id=activity_id).delete()
    messages.success(request, '已取消活动报名。')
    return redirect('activity_detail', activity_id=activity_id)



def activity_detail(request, activity_id):
    """
    活动详情视图
    参数：
    - request: HTTP请求对象
    - activity_id: 活动ID
    返回值：
    - 渲染活动详情页面，包含活动信息和照片
    业务逻辑：
    1. 获取活动对象，不存在则返回404
    2. 查询活动的所有照片
    3. 如果用户已登录：
       - 检查用户是否是该社团成员
       - 检查用户是否已报名该活动
    4. 渲染活动详情页面
    """
    activity = get_object_or_404(ClubActivity.objects.select_related('club'), id=activity_id)
    privileged = request.user.is_authenticated and (request.user.is_staff or activity.club.president_id == request.user.pk)
    if activity.status not in (2, 4) and not privileged:
        raise Http404('活动尚未公开。')
    # 获取该活动的所有照片
    gallery = ActivityGallery.objects.filter(activity=activity)

    is_member = False
    is_signed_up = False

    if request.user.is_authenticated:
        # 检查用户是否是该社团成员
        is_member = ClubMember.objects.filter(student=request.user, club=activity.club).exists()
        # 检查用户是否已报名该活动
        is_signed_up = ActivitySignup.objects.filter(student=request.user, activity=activity).exists()

    return render(request, 'management/activity_detail.html', {
        'activity': activity,
        'gallery': gallery,
        'is_member': is_member,
        'is_signed_up': is_signed_up,
    })



@login_required
@require_POST
def upload_club_images(request, club_id):
    club = get_object_or_404(Club, pk=club_id)
    if club.president_id != request.user.pk and not request.user.is_staff:
        raise PermissionDenied('仅社长及管理员可以上传照片。')
    images = request.FILES.getlist('images')
    stored = []
    try:
        if not images:
            raise ValidationError('请选择图片。')
        validate_uploads(images)
        with transaction.atomic():
            club = Club.objects.select_for_update().get(pk=club_id)
            if club.president_id != request.user.pk and not request.user.is_staff:
                raise PermissionDenied('社长已变更，请刷新页面。')
            for image in images:
                _save_upload(ClubGallery(club=club), 'image', image, stored)
        messages.success(request, '宣传照片已上传。')
    except ValidationError as exc:
        _cleanup_uploads(stored)
        messages.error(request, '；'.join(exc.messages))
    except PermissionDenied:
        _cleanup_uploads(stored)
        raise
    except Exception:
        _cleanup_uploads(stored)
        logger.exception('照片上传失败')
        messages.error(request, '上传失败，请检查图片格式、大小和数量后重试。')
    return redirect('club_manager', club_id=club_id)




@login_required
@require_POST
def delete_club_image(request, img_id):
    image = get_object_or_404(ClubGallery, pk=img_id)
    with transaction.atomic():
        club = Club.objects.select_for_update().get(pk=image.club_id)
        if club.president_id != request.user.pk and not request.user.is_staff:
            raise PermissionDenied('仅社长及管理员可以删除照片。')
        image.delete()
    messages.success(request, '宣传照片已删除。')
    return redirect('club_manager', club_id=image.club_id)



def activity_list(request):
    """
    活动列表视图，支持搜索
    参数：
    - request: HTTP请求对象
    返回值：
    - 渲染活动列表页面，包含搜索结果
    业务逻辑：
    1. 获取搜索关键词
    2. 查询已通过审批的活动（status=2）
    3. 应用搜索关键词筛选
    4. 对查询结果进行分页处理
    5. 渲染活动列表页面
    """
    query = request.GET.get('q', '')  # 搜索关键词
    # 只查询已通过审批的活动（status=2）
    activity_queryset = ClubActivity.objects.filter(status=2).order_by('-create_time')

    # 应用搜索关键词筛选
    if query:
        activity_queryset = activity_queryset.filter(name__icontains=query)

    # 分页处理，每页显示6个活动
    paginator = Paginator(activity_queryset, 6)
    page_number = request.GET.get('page')  # 当前页码
    page_obj = paginator.get_page(page_number)  # 获取当前页的活动列表

    return render(request, 'management/activity_list.html', {
        'page_obj': page_obj,
        'query': query  # 将搜索关键词传回前端，保持搜索框内容
    })

def _save_upload(instance, field_name, upload, stored):
    field = getattr(instance, field_name)
    field.save(upload.name, upload, save=False)
    stored.append((field.storage, field.name))
    instance.save()


def _cleanup_uploads(stored):
    for storage, name in stored:
        try:
            storage.delete(name)
        except Exception:
            logger.exception('清理未提交的上传文件失败')


@login_required
def download_attachment(request, attachment_id):
    attachment = get_object_or_404(ActivityAttachment.objects.select_related('activity__club'), pk=attachment_id)
    club = attachment.activity.club
    if not request.user.is_staff and club.president_id != request.user.pk:
        raise PermissionDenied('仅社长及管理员可以下载申请材料。')
    try:
        return FileResponse(attachment.file.open('rb'), as_attachment=True)
    except FileNotFoundError as exc:
        raise Http404('附件不存在。') from exc
