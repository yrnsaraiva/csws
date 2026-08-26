from django import forms
from .models import NutritionLog


class NutritionLogForm(forms.ModelForm):
    """Formulário para notas no log alimentar."""

    class Meta:
        model = NutritionLog
        fields = ["notes"]
        widgets = {
            "notes": forms.Textarea(attrs={
                "rows": 2,
                "placeholder": "Observações sobre a refeição...",
                "class": "w-full bg-dark-surface border border-dark-border rounded-xl px-4 py-3 text-sm text-white",
            }),
        }