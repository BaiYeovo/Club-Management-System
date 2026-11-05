import logging

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import ActivityAttachment, ActivityGallery, ActivitySignup, ClubGallery, ClubMember

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=ClubMember)
def cancel_members_signups(sender, instance, **kwargs):
    ActivitySignup.objects.filter(
        student_id=instance.student_id, activity__club_id=instance.club_id,
    ).delete()


@receiver(post_delete, sender=ClubGallery)
@receiver(post_delete, sender=ActivityGallery)
@receiver(post_delete, sender=ActivityAttachment)
def delete_uploaded_file(sender, instance, **kwargs):
    field = instance.file if sender is ActivityAttachment else instance.image
    if field.name:
        storage, name = field.storage, field.name

        def cleanup():
            try:
                storage.delete(name)
            except OSError:
                logger.exception('删除上传文件失败：%s', name)

        transaction.on_commit(cleanup)
