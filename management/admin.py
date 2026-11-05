from django.contrib import admin
from django import forms
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.forms.models import BaseInlineFormSet
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.contrib import messages
from django.http import HttpResponseRedirect
from .models import Student, Club, ClubMember, ClubActivity, ActivityGallery, ActivityAttachment
from django.utils.html import format_html


class BusinessRuleAdmin(admin.ModelAdmin):
    # 表单校验后仍需在保存时加锁复查；并发竞争失败时回到表单显示提示。
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except ValidationError as exc:
            messages.error(request, '；'.join(exc.messages))
            return HttpResponseRedirect(request.path)

    def delete_view(self, request, object_id, extra_context=None):
        try:
            return super().delete_view(request, object_id, extra_context)
        except ValidationError as exc:
            messages.error(request, '；'.join(exc.messages))
            return HttpResponseRedirect(request.path)

    def response_action(self, request, queryset):
        try:
            return super().response_action(request, queryset)
        except ValidationError as exc:
            messages.error(request, '；'.join(exc.messages))
            return HttpResponseRedirect(request.path)


class StudentCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Student
        fields = ('student_id', 'nickname', 'email')


class StudentChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = Student
        fields = '__all__'


@admin.register(Student)
class StudentAdmin(UserAdmin):
    form = StudentChangeForm
    add_form = StudentCreationForm
    list_display = ('student_id', 'nickname', 'email', 'user_state', 'is_staff', 'date_joined')
    search_fields = ('student_id', 'nickname', 'email')
    list_filter = ('user_state', 'is_staff', 'is_active')
    ordering = ('student_id',)
    fieldsets = (
        (None, {'fields': ('student_id', 'password')}),
        ('学生信息', {'fields': ('nickname', 'email', 'user_state')}),
        ('权限', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = ((None, {'fields': ('student_id', 'nickname', 'email', 'password1', 'password2')}),)


class ClubMemberInline(admin.TabularInline):
    model = ClubMember
    extra = 0
    fields = ('student', 'role', 'join_date')
    readonly_fields = fields
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Club)
class ClubAdmin(BusinessRuleAdmin):
    list_display = ('name', 'president', 'category', 'member_count', 'establish_date')
    search_fields = ('name', 'category')
    readonly_fields = ('member_count',)
    inlines = [ClubMemberInline]


class UploadInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        uploads = 0
        for form in self.forms:
            if not hasattr(form, 'cleaned_data') or form.cleaned_data.get('DELETE'):
                continue
            for field in ('image', 'file'):
                value = form.cleaned_data.get(field)
                if value is not None and hasattr(value, 'content_type'):
                    uploads += 1
        if uploads > 10:
            raise ValidationError('每次最多上传 10 个文件。')


class ActivityGalleryInline(admin.TabularInline):
    """
    活动照片行内显示类
    功能：允许在活动审批页面直接查看和管理活动照片
    """
    model = ActivityGallery
    formset = UploadInlineFormSet
    extra = 1
    readonly_fields = ('image_preview',)

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="width: 100px; height: auto;" />', obj.image.url)
        return "暂无照片"

    image_preview.short_description = "照片预览"


# --- 新增：活动附件行内显示类 ---
class ActivityAttachmentInline(admin.TabularInline):
    """
    活动附件行内显示类
    功能：允许在活动审批页面直接下载查看 PDF/Word 申请材料
    """
    model = ActivityAttachment
    formset = UploadInlineFormSet
    extra = 0  # 附件通常是上传好的，不需要默认多余的空白框
    readonly_fields = ('download_link',)  # 设置下载链接为只读

    def download_link(self, obj):
        """
        生成下载链接
        """
        if obj.file:
            # 获取文件名
            file_name = obj.file.name.split('/')[-1]
            return format_html('<a href="{}" target="_blank">点击下载/预览: {}</a>', reverse('download_attachment', args=[obj.pk]), file_name)
        return "无附件"

    download_link.short_description = "附件下载"


@admin.register(ClubActivity)
class ClubActivityAdmin(BusinessRuleAdmin):
    """
    社团活动后台管理类，包含活动审批功能
    """
    # 列表页显示内容
    list_display = ('name', 'club', 'status_color', 'start_time', 'end_time', 'current_participants')
    # 筛选器
    list_filter = ('status', 'club', 'start_time')
    readonly_fields = ('current_participants',)
    # 搜索框
    search_fields = ('name',)

    # --- 修改点：在 inlines 中加入 ActivityAttachmentInline ---
    # 这样审批时既能看图片，也能下载附件文档
    inlines = [ActivityGalleryInline, ActivityAttachmentInline]

    def status_color(self, obj):
        colors = {
            1: ('#FF9800', '待审批'),
            2: ('#4CAF50', '已通过'),
            3: ('#F44336', '已拒绝'),
            4: ('#9E9E9E', '已结束'),
        }
        color, text = colors.get(obj.status, ('#000', '未知'))
        return format_html('<b style="color: {};">{}</b>', color, text)

    status_color.short_description = "审批状态"

    # 核心：批量审批动作
    actions = ['make_approved', 'make_rejected']

    def make_approved(self, request, queryset):
        rows_updated = queryset.update(status=2)
        self.message_user(request, f"成功批准了 {rows_updated} 个活动申请")

    make_approved.short_description = "批量通过选中的活动申请"

    def make_rejected(self, request, queryset):
        rows_updated = queryset.update(status=3)
        self.message_user(request, f"已拒绝 {rows_updated} 个活动申请")

    make_rejected.short_description = "批量拒绝选中的活动申请"


@admin.register(ClubMember)
class ClubMemberAdmin(BusinessRuleAdmin):
    list_display = ('student', 'club', 'role', 'join_date')
    list_filter = ('club',)
    readonly_fields = ('role',)

    def get_readonly_fields(self, request, obj=None):
        return ('role', 'student', 'club') if obj else ('role',)

    def get_deleted_objects(self, objs, request):
        deleted, counts, permissions, protected = super().get_deleted_objects(objs, request)
        for member in objs:
            if member.student_id == member.club.president_id:
                protected.append('社长成员关系：请先转让社长职位。')
        return deleted, counts, permissions, protected


# 修改后台界面配置
admin.site.site_header = "社团管理系统后台"
admin.site.site_title = "社团管理后台"
admin.site.index_title = "系统资源管理"