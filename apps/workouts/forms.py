from django import forms
from .models import ExerciseLog, WorkoutLog


class ExerciseLogForm(forms.ModelForm):
    """Formulário para registrar uma série."""

    class Meta:
        model = ExerciseLog
        fields = ["weight_kg", "reps_done", "completed", "notes"]
        widgets = {
            "weight_kg": forms.NumberInput(attrs={
                "step": "0.5",
                "placeholder": "—",
                "class": "w-full bg-dark-surface border border-dark-border rounded-lg px-3 py-2 text-center text-sm text-white",
            }),
            "reps_done": forms.NumberInput(attrs={
                "placeholder": "12",
                "class": "w-full bg-dark-surface border border-dark-border rounded-lg px-3 py-2 text-center text-sm text-white",
            }),
            "notes": forms.TextInput(attrs={
                "placeholder": "Observações...",
                "class": "w-full bg-dark-surface border border-dark-border rounded-lg px-3 py-2 text-sm text-white",
            }),
        }


class WorkoutNotesForm(forms.ModelForm):
    """Notas gerais da sessão de treino."""

    class Meta:
        model = WorkoutLog
        fields = ["notes"]
        widgets = {
            "notes": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Como foi o treino?",
                "class": "w-full bg-dark-surface border border-dark-border rounded-xl px-4 py-3 text-sm text-white",
            }),
        }