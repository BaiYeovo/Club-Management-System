from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.db.models import F, Q
from django.utils import timezone

from .validators import validate_image, validate_document
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin


class StudentManager(BaseUserManager):
    """
    学生用户管理器, 处理自定义用户的创建
    用于管理Student模型的创建, 包括普通用户和超级用户
    """
    
    def create_user(self, student_id, password=None, **extra_fields):
        """
        创建普通学生用户
        参数：
        - student_id: 学号, 作为用户的唯一标识
        - password: 密码, 会自动加密存储
        - extra_fields: 其他额外字段
        返回值：
        - 创建的Student实例
        异常：
        - ValueError: 当学号为空时抛出
        """
        if not student_id:
            raise ValueError('学号必须填写')
        extra_fields.setdefault('is_active', True)
        extra_fields['email'] = self.normalize_email(extra_fields.get('email', '')).lower()
        user = self.model(student_id=student_id.strip(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, student_id, password=None, **extra_fields):
        """
        创建超级用户
        参数：
        - student_id: 学号
        - password: 密码
        - extra_fields: 其他额外字段
        返回值：
        - 创建的超级用户实例
        说明：
        自动设置is_staff和is_superuser为True
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        if not extra_fields['is_staff'] or not extra_fields['is_superuser']:
            raise ValueError('超级用户必须设置 is_staff 和 is_superuser。')
        return self.create_user(student_id, password, **extra_fields)


class Student(AbstractBaseUser, PermissionsMixin):
    """
    学生用户模型, 继承自Django认证基类
    自定义认证模型, 使用学号作为登录标识
    """
    
    # 学号，作为主键
    student_id = models.CharField(max_length=20, primary_key=True, verbose_name='学号')
    # 邮箱地址，必须唯一
    email = models.EmailField(max_length=100, unique=True, verbose_name='邮箱')
    # 学生姓名
    nickname = models.CharField(max_length=16, verbose_name='姓名')
    # 用户状态：1-正常，2-冻结
    user_state = models.IntegerField(default=1, verbose_name='状态(1:正常, 2:冻结)')

    # Django认证系统字段
    is_staff = models.BooleanField(default=False, verbose_name='是否拥有后台访问权限')
    is_active = models.BooleanField(default=True, verbose_name='是否有效')
    date_joined = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    # 关联自定义管理器
    objects = StudentManager()

    # 配置登录字段
    USERNAME_FIELD = 'student_id'  # 登录使用的唯一标识字段
    REQUIRED_FIELDS = ['nickname', 'email']  # 命令行创建超级用户时必填项

    class Meta:
        verbose_name = '学生'
        verbose_name_plural = verbose_name

    def __str__(self):
        """
        字符串表示, 返回学生姓名和学号
        
        返回值：
        - 格式化的学生信息字符串
        """
        return f"{self.nickname}({self.student_id})"


class Club(models.Model):
    """
    社团模型

    表示学校中的社团信息
    """

    # 社团名称
    name = models.CharField(max_length=128, verbose_name='社团名称')
    # 社团人数，自动维护

    # 社长关联到Student模型，社团删除时置空
    president = models.ForeignKey(
        Student,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='社长',
        related_name='presided_clubs'  # 反向关联名称
    )
    # 社团成立日期
    establish_date = models.DateField(verbose_name='社团成立日期')
    # 社团类别
    category = models.CharField(max_length=128, verbose_name='社团类别')
    # 社团详细描述
    detail = models.TextField(verbose_name='社团描述')

    @property
    def member_count(self):
        return self.clubmember_set.count()

    def clean(self):
        super().clean()
        if self.president_id:
            memberships = ClubMember.objects.filter(student_id=self.president_id)
            if self.pk:
                memberships = memberships.exclude(club_id=self.pk)
            if memberships.count() >= 2:
                raise ValidationError({'president': '该学生已加入两个其他社团。'})

    def save(self, *args, **kwargs):
        # 所有成员写入先锁学生，再锁社团，确保加入上限可串行检查。
        with transaction.atomic():
            if self.president_id:
                Student.objects.select_for_update().get(pk=self.president_id)
            if self.pk:
                Club.objects.select_for_update().get(pk=self.pk)
            self.clean()
            super().save(*args, **kwargs)
            if self.president_id:
                ClubMember.objects.get_or_create(student_id=self.president_id, club=self)

    class Meta:
        db_table = 'management_club'
        ordering = ['name']
        verbose_name = '社团'
        verbose_name_plural = verbose_name

    def __str__(self):
        """
        字符串表示, 返回社团名称

        返回值：
        - 社团名称字符串
        """
        return self.name


class ClubGallery(models.Model):
    """
    社团宣传图模型

    用于存储社团的宣传照片
    """

    # 关联社团, 社团删除时照片也随之删除
    club = models.ForeignKey(
        'Club', 
        on_delete=models.CASCADE, 
        related_name='gallery'  # 反向关联名称
    )
    image = models.ImageField(upload_to='club_photos/', validators=[validate_image])
    upload_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "社团宣传图"
        verbose_name_plural = verbose_name


class MembershipQuerySet(models.QuerySet):
    def delete(self):
        with transaction.atomic():
            rows = list(self.values_list('student_id', 'club_id'))
            list(Student.objects.select_for_update().filter(pk__in=[r[0] for r in rows]).order_by('pk'))
            list(Club.objects.select_for_update().filter(pk__in=[r[1] for r in rows]).order_by('pk'))
            if self.filter(student_id=F('club__president_id')).exists():
                raise ValidationError('不能移除社长，请先在社团中转让社长职位。')
            return super().delete()


class ClubMember(models.Model):
    """
    社团成员模型

    记录学生与社团之间的关联关系
    """

    # 关联学生，学生删除时自动删除关联记录
    student = models.ForeignKey(Student, on_delete=models.CASCADE, verbose_name='学生')
    # 关联社团，社团删除时自动删除关联记录
    club = models.ForeignKey(Club, on_delete=models.CASCADE, verbose_name='社团')
    # 加入日期，自动生成
    join_date = models.DateTimeField(auto_now_add=True, verbose_name='加入日期')
    # 角色：1-普通成员，2-社长


    objects = MembershipQuerySet.as_manager()

    @property
    def role(self):
        return 2 if self.student_id == self.club.president_id else 1

    def clean(self):
        super().clean()
        if self.pk:
            original = ClubMember.objects.filter(pk=self.pk).first()
            if original and (original.student_id != self.student_id or original.club_id != self.club_id):
                raise ValidationError('成员关系不能转移，请删除后重新添加。')
        if self.student_id and self.club_id:
            others = ClubMember.objects.filter(student_id=self.student_id).exclude(pk=self.pk)
            if others.count() >= 2:
                raise ValidationError('每位学生最多加入两个社团。')

    def save(self, *args, **kwargs):
        with transaction.atomic():
            Student.objects.select_for_update().get(pk=self.student_id)
            Club.objects.select_for_update().get(pk=self.club_id)
            self.full_clean()
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return ClubMember.objects.filter(pk=self.pk).delete()

    class Meta:
        db_table = 'management_club_member'
        unique_together = ('student', 'club')  # 联合唯一索引，确保一个学生在一个社团中只能有一条记录
        verbose_name = '社团成员关系'
        verbose_name_plural = verbose_name


class ClubActivity(models.Model):
    """
    社团活动模型

    表示社团举办的活动信息
    """

    STATUS_CHOICES = (
        (1, '待审批'),
        (2, '已通过'),
        (3, '已拒绝'),
        (4, '已结束'),
    )
    
    # 所属社团，社团删除时自动删除活动
    club = models.ForeignKey(Club, on_delete=models.CASCADE, verbose_name='所属社团')
    # 活动名称
    name = models.CharField(max_length=128, verbose_name='活动名称')
    # 活动详细描述
    description = models.TextField(verbose_name='活动描述')
    # 活动开始时间
    start_time = models.DateTimeField(verbose_name='开始时间')
    # 活动结束时间
    end_time = models.DateTimeField(verbose_name='结束时间')
    # 活动最大参与人数
    max_participants = models.IntegerField(verbose_name='最大参与人数')
    # 当前参与人数，自动维护

    # 活动状态，默认待审批
    status = models.IntegerField(choices=STATUS_CHOICES, default=1, verbose_name='状态')
    # 创建时间，自动生成
    create_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    @property
    def current_participants(self):
        return self.signed_students.count()

    @property
    def registration_open(self):
        return self.status == 2 and self.start_time > timezone.now()

    def clean(self):
        super().clean()
        if self.pk and ClubActivity.objects.filter(pk=self.pk).exclude(club_id=self.club_id).exists():
            raise ValidationError({'club': '活动所属社团不能修改，请重新创建活动。'})
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({'end_time': '结束时间必须晚于开始时间。'})
        if self.max_participants is not None and self.max_participants < 1:
            raise ValidationError({'max_participants': '参与人数必须大于零。'})
        if self.pk and self.max_participants is not None and self.current_participants > self.max_participants:
            raise ValidationError({'max_participants': '名额不能少于已报名人数。'})

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.pk:
                ClubActivity.objects.select_for_update().get(pk=self.pk)
            self.full_clean()
            return super().save(*args, **kwargs)

    class Meta:
        db_table = 'management_club_activity'
        ordering = ['-start_time']  # 默认按开始时间倒序排序
        constraints = [
            models.CheckConstraint(condition=Q(max_participants__gte=1), name='activity_capacity_positive'),
            models.CheckConstraint(condition=Q(end_time__gt=F('start_time')), name='activity_time_order'),
        ]
        verbose_name = '社团活动'
        verbose_name_plural = verbose_name

    def __str__(self):
        """
        字符串表示, 返回活动名称

        返回值：
        - 活动名称字符串
        """
        return self.name


class ActivityGallery(models.Model):
    """
    活动照片库模型

    用于存储社团活动的照片
    """

    # 所属活动, 活动删除时自动删除照片  
    activity = models.ForeignKey(ClubActivity, on_delete=models.CASCADE, verbose_name='所属活动')
    # 照片文件, 上传到按日期组织的目录下
    image = models.ImageField(upload_to='activity_gallery/%Y/%m/%d/', verbose_name='照片', validators=[validate_image])
    # 照片描述, 可选
    description = models.CharField(max_length=255, blank=True, verbose_name='描述')
    # 上传时间, 自动生成
    upload_time = models.DateTimeField(auto_now_add=True, verbose_name='上传时间')

    class Meta:
        db_table = 'management_activity_gallery'
        verbose_name = '活动照片'
        verbose_name_plural = verbose_name


class ActivityAttachment(models.Model):
    """
    存放活动申请的PDF/Word文档
    """
    activity = models.ForeignKey(ClubActivity, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='activity_docs/%Y/%m/%d/', verbose_name='申请文件', validators=[validate_document])
    upload_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'management_activity_attachment'
        verbose_name = '活动附件'
        verbose_name_plural = verbose_name


class ActivitySignup(models.Model):
    """
    活动报名模型

    记录学生报名参加活动的信息
    """

    # 关联学生, 学生删除时自动删除报名记录
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        verbose_name='学生',
        related_name='activity_signups'  # 反向关联名称
    )
    # 关联活动, 活动删除时自动删除报名记录
    activity = models.ForeignKey(
        ClubActivity,
        on_delete=models.CASCADE,
        verbose_name='活动',
        related_name='signed_students'  # 反向关联名称
    )
    # 报名时间, 自动生成
    signup_time = models.DateTimeField(auto_now_add=True, verbose_name='报名时间')

    def save(self, *args, **kwargs):
        with transaction.atomic():
            Student.objects.select_for_update().get(pk=self.student_id)
            club_id = ClubActivity.objects.values_list('club_id', flat=True).get(pk=self.activity_id)
            Club.objects.select_for_update().get(pk=club_id)
            activity = ClubActivity.objects.select_for_update().get(pk=self.activity_id)
            if not self._state.adding:
                raise ValidationError('报名记录不可修改，请取消后重新报名。')
            if not ClubMember.objects.filter(student_id=self.student_id, club_id=club_id).exists():
                raise ValidationError('您不是该社团的成员。')
            if not activity.registration_open:
                raise ValidationError('活动未通过审批或报名已经截止。')
            if activity.current_participants >= activity.max_participants:
                raise ValidationError('活动名额已满。')
            self.full_clean()
            return super().save(*args, **kwargs)

    class Meta:
        db_table = 'management_activity_signup'
        # 联合唯一索引：确保一个学生对同一个活动只能报名一次
        unique_together = ('student', 'activity')
        ordering = ['-signup_time']  # 默认按报名时间倒序排序
        verbose_name = '活动报名记录'
        verbose_name_plural = verbose_name

    def __str__(self):
        """
        字符串表示, 返回学生报名活动的信息

        返回值：
        - 格式化的报名信息字符串
        """
        return f"{self.student.nickname} 报名了 {self.activity.name}"


