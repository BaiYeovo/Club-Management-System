from django import forms
from django.contrib.auth.password_validation import validate_password

from .models import ClubActivity, Student


class SignupForm(forms.ModelForm):
    password = forms.CharField(strip=False, widget=forms.PasswordInput)
    repeat_password = forms.CharField(strip=False, widget=forms.PasswordInput)

    class Meta:
        model = Student
        fields = ('student_id', 'nickname', 'email')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if Student.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('该邮箱已注册。')
        return email

    def clean(self):
        data = super().clean()
        password = data.get('password')
        if password != data.get('repeat_password'):
            self.add_error('repeat_password', '两次密码输入不一致。')
        if password:
            user = Student(**{k: data.get(k, '') for k in self.Meta.fields})
            validate_password(password, user)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class PasswordChangeForm(forms.Form):
    old_password = forms.CharField(strip=False, widget=forms.PasswordInput)
    new_password = forms.CharField(strip=False, widget=forms.PasswordInput)
    repeat_password = forms.CharField(strip=False, widget=forms.PasswordInput)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_old_password(self):
        value = self.cleaned_data['old_password']
        if not self.user.check_password(value):
            raise forms.ValidationError('原密码错误。')
        return value

    def clean(self):
        data = super().clean()
        password = data.get('new_password')
        if password != data.get('repeat_password'):
            self.add_error('repeat_password', '两次新密码输入不一致。')
        if password:
            validate_password(password, self.user)
        return data


class ActivityForm(forms.ModelForm):
    class Meta:
        model = ClubActivity
        fields = ('name', 'description', 'start_time', 'end_time', 'max_participants')
