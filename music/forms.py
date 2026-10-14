"""Forms for Room creation, onboarding, room settings, and moderator access."""

from django import forms
from .models import Room, RoomSettings


class JoinRoomForm(forms.Form):
    """Form used on welcome screen to enter employee name and optional room code."""

    display_name = forms.CharField(
        max_length=50,
        required=True,
        label="Your Display Name",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g. Alex Rivera",
                "autocomplete": "name",
                "autofocus": "autofocus",
            }
        ),
    )
    room_code = forms.CharField(
        max_length=12,
        required=False,
        label="Room Code",
        widget=forms.TextInput(
            attrs={
                "class": "form-control uppercase-input",
                "placeholder": "Auto-joins your office network if blank",
                "autocomplete": "off",
            }
        ),
    )

    def clean_display_name(self):
        name = self.cleaned_data.get("display_name", "").strip()
        if len(name) < 2:
            raise forms.ValidationError("Name must be at least 2 characters.")
        return name

    def clean_room_code(self):
        code = self.cleaned_data.get("room_code", "").strip().upper()
        return code


class CreateRoomForm(forms.Form):
    """Form to explicitly create a named room."""

    name = forms.CharField(
        max_length=100,
        required=True,
        label="Room Name",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g. HQ 3rd Floor / Design Studio",
            }
        ),
    )
    moderator_pin = forms.CharField(
        max_length=20,
        required=False,
        label="Moderator PIN (optional)",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Set a PIN to lock moderator controls",
            }
        ),
    )
    bind_to_my_ip = forms.BooleanField(
        required=False,
        initial=True,
        label="Bind to current office network IP so colleagues join automatically",
    )


class RoomSettingsForm(forms.ModelForm):
    """Form for room moderators to adjust fair-play queue limits and intervals."""

    class Meta:
        model = RoomSettings
        fields = [
            "max_active_songs_per_user",
            "user_song_cooldown_seconds",
            "fair_turn_mode",
            "auto_advance",
            "poll_interval_ms",
        ]
        widgets = {
            "max_active_songs_per_user": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 20}),
            "user_song_cooldown_seconds": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 600}),
            "poll_interval_ms": forms.NumberInput(attrs={"class": "form-control", "min": 1000, "max": 30000, "step": 500}),
            "fair_turn_mode": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            "auto_advance": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
        }


class ModeratorLoginForm(forms.Form):
    """Form to claim moderator role in a protected room."""

    pin = forms.CharField(
        required=True,
        label="Enter Moderator PIN",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter room PIN",
                "autofocus": "autofocus",
            }
        ),
    )
