"""上传内容校验；限制在写入存储之前执行。"""
import warnings
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_SIZE = 5 * 1024 * 1024
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024
MAX_UPLOAD_COUNT = 10


def validate_image(file):
    if file.size > MAX_IMAGE_SIZE:
        raise ValidationError('每张图片不能超过 5 MB。')
    try:
        file.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(file) as image:
                if image.format not in {'JPEG', 'PNG', 'WEBP', 'GIF'}:
                    raise ValidationError('图片仅支持 JPEG、PNG、WebP 和 GIF。')
                expected = {'JPEG': {'.jpg', '.jpeg'}, 'PNG': {'.png'},
                            'WEBP': {'.webp'}, 'GIF': {'.gif'}}
                if Path(file.name).suffix.lower() not in expected[image.format]:
                    raise ValidationError('图片扩展名与实际格式不符。')
                image.verify()
    except (UnidentifiedImageError, OSError, ValueError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValidationError('图片文件损坏或尺寸过大。') from exc
    finally:
        file.seek(0)


def validate_document(file):
    if file.size > MAX_DOCUMENT_SIZE:
        raise ValidationError('每份附件不能超过 10 MB。')
    suffix = Path(file.name).suffix.lower()
    try:
        file.seek(0)
        signature = file.read(8)
        valid = False
        if suffix == '.pdf':
            valid = signature.startswith(b'%PDF-')
        elif suffix == '.doc':
            valid = signature == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
        elif suffix == '.docx':
            with ZipFile(file) as archive:
                names = set(archive.namelist())
                valid = {'[Content_Types].xml', 'word/document.xml'} <= names
                if sum(i.file_size for i in archive.infolist()) > 50 * 1024 * 1024:
                    valid = False
                if any('vbaProject' in name for name in names):
                    valid = False
        if not valid:
            raise ValidationError('附件必须为格式有效的 PDF、DOC 或 DOCX 文件。')
    except (BadZipFile, OSError, ValueError) as exc:
        raise ValidationError('附件文件损坏。') from exc
    finally:
        file.seek(0)


def validate_uploads(images, documents=()):
    if len(images) > MAX_UPLOAD_COUNT or len(documents) > MAX_UPLOAD_COUNT:
        raise ValidationError('每次最多上传 10 张图片和 10 份附件。')
    for file in images:
        validate_image(file)
    for file in documents:
        validate_document(file)
