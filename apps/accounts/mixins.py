# accounts/mixins.py
from django.contrib.auth.mixins import UserPassesTestMixin


class CoachRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_coach


class ClientRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_client