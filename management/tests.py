import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .admin import ClubMemberAdmin, StudentCreationForm
from .forms import PasswordChangeForm, SignupForm
from .models import (ActivityAttachment, ActivityGallery, ActivitySignup, Club,
                     ClubActivity, ClubGallery, ClubMember, Student)
from .validators import validate_document, validate_image, validate_uploads


def student(sid):
    return Student.objects.create_user(sid, 'Good-password-92!', email=f'{sid}@example.com', nickname=sid)


def club(name, president=None):
    return Club.objects.create(name=name, president=president,
        establish_date=timezone.now().date(), category='科技', detail='社团介绍')


def activity(owner, **kwargs):
    data = dict(club=owner, name='活动', description='活动说明',
                start_time=timezone.now() + timedelta(days=2),
                end_time=timezone.now() + timedelta(days=3),
                max_participants=2, status=2)
    data.update(kwargs)
    return ClubActivity.objects.create(**data)


def image_upload(name='photo.png'):
    buffer = BytesIO()
    Image.new('RGB', (16, 16), '#7398d0').save(buffer, 'PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


class BusinessTests(TestCase):
    def setUp(self):
        self.owner = student('owner')
        self.member = student('member')
        self.other = student('other')
        self.club = club('测试社团', self.owner)
        self.membership = ClubMember.objects.create(student=self.member, club=self.club)
        self.activity = activity(self.club)
        self.client.force_login(self.member)

    def test_members_cannot_remove_others(self):
        response = self.client.post(reverse('delete_member', args=[self.membership.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ClubMember.objects.filter(pk=self.membership.pk).exists())

    def test_president_cannot_be_removed(self):
        self.client.force_login(self.owner)
        president = ClubMember.objects.get(student=self.owner, club=self.club)
        self.client.post(reverse('delete_member', args=[president.pk]))
        self.assertTrue(ClubMember.objects.filter(pk=president.pk).exists())
        with self.assertRaises(ValidationError):
            ClubMember.objects.filter(pk=president.pk).delete()

    def test_president_can_remove_member_and_signups(self):
        ActivitySignup.objects.create(student=self.member, activity=self.activity)
        self.client.force_login(self.owner)
        self.assertRedirects(self.client.post(reverse('delete_member', args=[self.membership.pk])),
                             reverse('club_manager', args=[self.club.pk]))
        self.assertFalse(ActivitySignup.objects.filter(student=self.member).exists())
        self.assertEqual(self.club.member_count, 1)
        self.assertEqual(self.activity.current_participants, 0)

    def test_member_list_is_private(self):
        url = reverse('show_members', args=[self.club.pk])
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.member)
        self.assertContains(self.client.get(url), self.member.student_id)

    def test_manager_denial_is_403_instead_of_route_error(self):
        self.assertEqual(self.client.get(reverse('club_manager', args=[self.club.pk])).status_code, 403)

    def test_mutations_require_post(self):
        image = ClubGallery.objects.create(club=self.club, image='club_photos/not-present.png')
        routes = [('join_club', self.club.pk), ('quit_club', self.club.pk),
                  ('signup_activity', self.activity.pk), ('cancel_signup', self.activity.pk),
                  ('delete_member', self.membership.pk), ('delete_club_image', image.pk),
                  ('upload_club_images', self.club.pk), ('submit_material', self.club.pk)]
        for name, pk in routes:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name, args=[pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)

    def test_csrf_required_for_mutations(self):
        secure_client = Client(enforce_csrf_checks=True)
        secure_client.force_login(self.member)
        self.assertEqual(secure_client.post(reverse('quit_club', args=[self.club.pk])).status_code, 403)
        self.assertTrue(ClubMember.objects.filter(pk=self.membership.pk).exists())

    def test_unapproved_and_past_activities_cannot_be_joined(self):
        for status in (1, 3, 4):
            event = activity(self.club, status=status)
            self.client.post(reverse('signup_activity', args=[event.pk]))
            self.assertFalse(ActivitySignup.objects.filter(activity=event).exists())
        event = activity(self.club, start_time=timezone.now()-timedelta(days=1))
        self.client.post(reverse('signup_activity', args=[event.pk]))
        self.assertEqual(event.current_participants, 0)

    def test_nonmember_cannot_signup(self):
        with self.assertRaises(ValidationError):
            ActivitySignup.objects.create(student=self.other, activity=self.activity)

    def test_unapproved_details_private(self):
        event = activity(self.club, status=1)
        url = reverse('activity_detail', args=[event.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_duplicate_and_full_signup(self):
        self.activity.max_participants = 1
        self.activity.save()
        ActivitySignup.objects.create(student=self.member, activity=self.activity)
        for user in (self.member, self.owner):
            with self.assertRaises(ValidationError):
                ActivitySignup.objects.create(student=user, activity=self.activity)
        self.assertEqual(self.activity.current_participants, 1)

    def test_cancel_and_quit_derive_counts(self):
        self.client.post(reverse('signup_activity', args=[self.activity.pk]))
        self.assertEqual(self.activity.current_participants, 1)
        self.client.post(reverse('cancel_signup', args=[self.activity.pk]))
        self.assertEqual(self.activity.current_participants, 0)
        ActivitySignup.objects.create(student=self.member, activity=self.activity)
        self.client.post(reverse('quit_club', args=[self.club.pk]))
        self.assertEqual(self.activity.current_participants, 0)
        self.assertEqual(self.club.member_count, 1)

    def test_membership_limit_applies_to_admin_model_writes(self):
        ClubMember.objects.create(student=self.member, club=club('第二社团'))
        with self.assertRaises(ValidationError):
            ClubMember.objects.create(student=self.member, club=club('第三社团'))

    def test_president_transfer_and_auto_membership(self):
        old = ClubMember.objects.get(student=self.owner, club=self.club)
        self.club.president = self.other
        self.club.save()
        old.refresh_from_db()
        self.assertEqual(old.role, 1)
        self.assertEqual(ClubMember.objects.get(student=self.other, club=self.club).role, 2)
        self.assertEqual(self.club.member_count, 3)

    def test_president_transfer_respects_membership_limit(self):
        for name in ('甲', '乙'):
            ClubMember.objects.create(student=self.other, club=club(name))
        self.club.president = self.other
        with self.assertRaises(ValidationError):
            self.club.save()
        self.club.refresh_from_db()
        self.assertEqual(self.club.president_id, self.owner.pk)

    def test_admin_bulk_delete_president_protected(self):
        model_admin = ClubMemberAdmin(ClubMember, AdminSite())
        request = type('Request', (), {'user': self.owner})()
        _, _, _, protected = model_admin.get_deleted_objects(
            ClubMember.objects.filter(student=self.owner), request)
        self.assertTrue(protected)

    def test_activity_validation(self):
        for overrides in ({'max_participants': 0}, {'max_participants': -1},
                          {'end_time': timezone.now()}):
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                activity(self.club, **overrides)

    def test_admin_counts_always_reflect_membership_records(self):
        self.membership.delete()
        self.assertEqual(self.club.member_count, 1)
        ClubMember.objects.create(student=self.other, club=self.club)
        self.assertEqual(self.club.member_count, 2)

    def test_signup_validation_and_email_uniqueness(self):
        data = dict(student_id='new', nickname='新用户', email='MEMBER@example.com',
                    password='Good-password-92!', repeat_password='Good-password-92!')
        self.assertFalse(SignupForm(data).is_valid())
        data['email'] = 'new@example.com'
        data['password'] = data['repeat_password'] = '123'
        self.assertFalse(SignupForm(data).is_valid())
        data['password'] = data['repeat_password'] = 'Different-password-92!'
        form = SignupForm(data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.save().check_password(data['password']))

    def test_password_change_validates_confirmation_and_strength(self):
        data = dict(old_password='Good-password-92!', new_password='123', repeat_password='123')
        self.assertFalse(PasswordChangeForm(self.member, data).is_valid())
        data.update(new_password='Another-password-42!', repeat_password='mismatch')
        self.assertFalse(PasswordChangeForm(self.member, data).is_valid())
        data['repeat_password'] = data['new_password']
        self.assertTrue(PasswordChangeForm(self.member, data).is_valid())
        self.client.post(reverse('set_password'), data)
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password(data['new_password']))
        self.assertEqual(self.client.get(reverse('my_clubs')).status_code, 200)

    def test_admin_user_creation_hashes_password(self):
        form = StudentCreationForm(dict(student_id='adminnew', nickname='新用户', email='adminnew@example.com',
            password1='Admin-password-92!', password2='Admin-password-92!'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.save().check_password('Admin-password-92!'))

    def test_pages_render_and_manager_controls_exist(self):
        self.client.force_login(self.owner)
        for name, args in [('homepage', []), ('set_password', []),
                           ('my_clubs', []), ('view_club_list', []), ('activity_list', []),
                           ('club_detail', [self.club.pk]), ('activity_detail', [self.activity.pk]),
                           ('club_manager', [self.club.pk]), ('show_members', [self.club.pk])]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('signup')).status_code, 200)
        self.assertEqual(self.client.get(reverse('login')).status_code, 200)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse('my_clubs')), reverse('club_manager', args=[self.club.pk]))
        response = self.client.get(reverse('club_manager', args=[self.club.pk]))
        self.assertContains(response, reverse('delete_member', args=[self.membership.pk]))
        self.assertContains(self.client.get(reverse('activity_list')), 'default_event.svg')

    def test_frame_protection_header_retained(self):
        self.assertEqual(self.client.get(reverse('homepage'))['X-Frame-Options'], 'DENY')
        self.assertEqual(self.client.get('/admin/login/')['X-Frame-Options'], 'SAMEORIGIN')


class UploadTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.media.cleanup)
        self.owner = student('owner')
        self.club = club('社团', self.owner)
        self.client.force_login(self.owner)

    def payload(self):
        return dict(name='活动申请', description='说明',
            start_time=(timezone.now()+timedelta(days=2)).strftime('%Y-%m-%dT%H:%M'),
            end_time=(timezone.now()+timedelta(days=3)).strftime('%Y-%m-%dT%H:%M'),
            max_participants='5')

    def test_reject_fake_image_and_document_before_creating_activity(self):
        payload = self.payload()
        payload['images'] = SimpleUploadedFile('fake.png', b'not an image')
        self.client.post(reverse('submit_material', args=[self.club.pk]), payload)
        self.assertEqual(ClubActivity.objects.count(), 0)
        with self.assertRaises(ValidationError):
            validate_document(SimpleUploadedFile('fake.pdf', b'not a pdf'))
        validate_document(SimpleUploadedFile('real.pdf', b'%PDF-1.7\n%%EOF'))

    def test_limits(self):
        with self.assertRaises(ValidationError):
            validate_uploads([image_upload() for _ in range(11)])
        file = SimpleUploadedFile('large.png', b'x'*(5*1024*1024+1))
        with self.assertRaises(ValidationError):
            validate_image(file)
        with self.assertRaises(ValidationError):
            validate_document(SimpleUploadedFile('large.pdf', b'x'*(10*1024*1024+1)))
        with self.assertRaises(ValidationError):
            validate_image(image_upload('wrong.jpg'))

    def test_valid_submission_and_attachment_permissions(self):
        payload = self.payload()
        payload.update(images=image_upload(), annex=SimpleUploadedFile('plan.pdf', b'%PDF-1.7\n%%EOF'))
        self.client.post(reverse('submit_material', args=[self.club.pk]), payload)
        event = ClubActivity.objects.get()
        self.assertEqual(event.status, 1)
        self.assertEqual(ActivityGallery.objects.count(), 1)
        attachment = ActivityAttachment.objects.get()
        url = reverse('download_attachment', args=[attachment.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        b''.join(response.streaming_content)
        self.client.force_login(student('outsider'))
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(attachment.file.url).status_code, 404)

    def test_failed_storage_rolls_back_database_and_cleans_files(self):
        from . import views
        original = views._save_upload
        calls = []
        def fail_second(instance, field_name, upload, stored):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError('模拟非 I/O 类型的存储故障')
            return original(instance, field_name, upload, stored)
        payload = self.payload()
        payload['images'] = [image_upload('first.png'), image_upload('second.png')]
        with self.assertLogs('management.views', level='ERROR'), patch('management.views._save_upload', side_effect=fail_second):
            self.client.post(reverse('submit_material', args=[self.club.pk]), payload)
        self.assertEqual(ClubActivity.objects.count(), 0)
        self.assertEqual(ActivityGallery.objects.count(), 0)
        self.assertFalse(any(p.is_file() for p in Path(self.media.name).rglob('*')))

    def test_photo_delete_removes_storage_file_after_commit(self):
        self.client.post(reverse('upload_club_images', args=[self.club.pk]), {'images': image_upload()})
        picture = ClubGallery.objects.get()
        path = Path(picture.image.path)
        self.assertTrue(path.exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('delete_club_image', args=[picture.pk]))
        self.assertFalse(path.exists())


class ConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_two_students_compete_for_last_slot(self):
        owner = student('owner')
        users = [student('first'), student('second')]
        target = club('并发活动', owner)
        event = activity(target, max_participants=1)
        for user in users:
            ClubMember.objects.create(student=user, club=target)
        barrier = Barrier(2)
        def signup(sid):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                ActivitySignup.objects.create(student_id=sid, activity_id=event.pk)
                return True
            except ValidationError:
                return False
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(signup, [u.pk for u in users]))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(event.current_participants, 1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_parallel_joins_respect_two_club_limit(self):
        user = student('student')
        clubs = [club(str(i)) for i in range(3)]
        ClubMember.objects.create(student=user, club=clubs[0])
        barrier = Barrier(2)
        def join(cid):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                ClubMember.objects.create(student_id=user.pk, club_id=cid)
                return True
            except ValidationError:
                return False
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(join, [c.pk for c in clubs[1:]]))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(ClubMember.objects.filter(student=user).count(), 2)


class MigrationTests(TransactionTestCase):
    def test_upgrade_and_reverse_reconstruct_derived_values(self):
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        old_target = [('management', '0004_activityattachment')]
        new_target = [('management', '0005_enforce_business_rules')]
        executor.migrate(old_target)
        try:
            apps = executor.loader.project_state(old_target).apps
            OldStudent = apps.get_model('management', 'Student')
            OldClub = apps.get_model('management', 'Club')
            OldMember = apps.get_model('management', 'ClubMember')
            OldActivity = apps.get_model('management', 'ClubActivity')
            OldSignup = apps.get_model('management', 'ActivitySignup')
            leader = OldStudent.objects.create(student_id='legacy_owner', nickname='社长', email='leader@example.com', password='!')
            member = OldStudent.objects.create(student_id='legacy_member', nickname='成员', email='member@example.com', password='!')
            legacy_club = OldClub.objects.create(name='旧社团', member_count=99, president_id=leader.pk,
                establish_date=timezone.now().date(), category='科技', detail='介绍')
            # 缺失的社长成员关系应在迁移时自动补齐。
            OldMember.objects.create(student_id=member.pk, club_id=legacy_club.pk, role=1)
            legacy_activity = OldActivity.objects.create(club_id=legacy_club.pk, name='旧活动', description='说明',
                start_time=timezone.now()+timedelta(days=2), end_time=timezone.now()+timedelta(days=3),
                max_participants=3, current_participants=99, status=2)
            OldSignup.objects.create(student_id=member.pk, activity_id=legacy_activity.pk)
            executor = MigrationExecutor(connection)
            executor.migrate(new_target)
            self.assertEqual(Club.objects.get(pk=legacy_club.pk).member_count, 2)
            self.assertEqual(ClubActivity.objects.get(pk=legacy_activity.pk).current_participants, 1)
            self.assertEqual(ClubMember.objects.get(student_id=leader.pk).role, 2)
            executor = MigrationExecutor(connection)
            executor.migrate(old_target)
            self.assertEqual(OldClub.objects.get(pk=legacy_club.pk).member_count, 2)
            self.assertEqual(OldActivity.objects.get(pk=legacy_activity.pk).current_participants, 1)
            self.assertEqual(OldMember.objects.get(student_id=leader.pk).role, 2)
        finally:
            MigrationExecutor(connection).migrate(new_target)
