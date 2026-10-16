from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth.models import Group
from unfold.admin import ModelAdmin
from unfold.decorators import display
from unfold.forms import AdminPasswordChangeForm

from apps.backoffice.utils import STATUS_COLORS
from .models import User

# Les groupes Django sont ré-enregistrés avec le thème Unfold
admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(ModelAdmin):
    search_fields = ["name"]
    filter_horizontal = ["permissions"]


class UserCreationForm(forms.ModelForm):
    """Création d'un compte depuis le back-office (identifiant = téléphone)."""
    password1 = forms.CharField(label="Mot de passe", widget=forms.PasswordInput, required=False,
                                help_text="Laisser vide pour un compte qui se connecte uniquement par OTP.")
    password2 = forms.CharField(label="Confirmation", widget=forms.PasswordInput, required=False)

    class Meta:
        model = User
        fields = ("phone", "first_name", "last_name", "user_type")

    def clean_password2(self):
        p1, p2 = self.cleaned_data.get("password1"), self.cleaned_data.get("password2")
        if p1 != p2:
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("password1"):
            user.set_password(self.cleaned_data["password1"])
        else:
            user.set_unusable_password()
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(
        label="Mot de passe",
        help_text='Les mots de passe ne sont pas stockés en clair. '
                  '<a href="../password/">Changer le mot de passe</a>.',
    )

    class Meta:
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = ["phone", "full_name", "user_type", "status_badge", "is_phone_verified", "is_staff", "created_at"]
    list_filter = ["user_type", "status", "is_staff", "is_active", "is_phone_verified"]
    search_fields = ["phone", "first_name", "last_name", "email"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at", "last_login"]
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Profil", {"fields": ("first_name", "last_name", "email", "avatar", "preferred_language")}),
        ("Compte", {"fields": ("user_type", "status", "is_phone_verified", "is_email_verified")}),
        ("Accès au back-office", {
            "classes": ["tab"],
            "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
        }),
        ("Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {"fields": ("phone", "first_name", "last_name", "user_type", "password1", "password2")}),
    )

    @display(description="Nom")
    def full_name(self, obj):
        return obj.get_full_name() or "—"

    @display(description="Statut", label=STATUS_COLORS)
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()
