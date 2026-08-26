from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, ClientProfile


class ClientRegistrationForm(UserCreationForm):
    """Formulário de registro de cliente."""
    first_name = forms.CharField(max_length=30, required=True, label="Nome")
    last_name = forms.CharField(max_length=30, required=True, label="Apelido")
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "password1", "password2"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]  # email como username
        user.email = self.cleaned_data["email"]
        user.role = User.Role.CLIENT
        if commit:
            user.save()
        return user


class ProfileUpdateForm(forms.ModelForm):
    """Edição de dados básicos do usuário."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "photo", "date_of_birth"]
        widgets = {
            "date_of_birth": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
        }


class ClientProfileForm(forms.ModelForm):
    """Edição de dados específicos do cliente."""

    class Meta:
        model = ClientProfile
        fields = ["height_cm", "weight_kg", "goal", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }