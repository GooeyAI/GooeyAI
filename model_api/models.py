from django.db import models
from django.utils import timezone


class ModelApiCall(models.Model):
    """
    One Model API call: its credit reservation, then its charge.

    The row is created when credits are reserved, before the call runs, and
    moves to exactly one of `settled` (charged once, by `invoice_id`) or
    `released` (nothing charged).
    """

    class Status(models.IntegerChoices):
        RESERVED = 1, "Reserved"
        SETTLING = 2, "Settling"
        SETTLED = 3, "Settled"
        RELEASED = 4, "Released"

    call_id = models.CharField(max_length=64, unique=True)
    status = models.IntegerField(choices=Status.choices, default=Status.RESERVED)

    workspace = models.ForeignKey(
        "workspaces.Workspace", on_delete=models.CASCADE, related_name="model_api_calls"
    )
    user = models.ForeignKey(
        "app_users.AppUser", on_delete=models.SET_NULL, null=True, blank=True
    )
    api_key = models.ForeignKey(
        "api_keys.ApiKey", on_delete=models.SET_NULL, null=True, blank=True
    )

    model = models.TextField(help_text="The model ID the client sent.")
    litellm_model = models.TextField(help_text="The LiteLLM routing ID it ran as.")
    call_type = models.CharField(max_length=64)

    reserved_credits = models.IntegerField(default=0)
    cost_usd = models.DecimalField(
        max_digits=18, decimal_places=10, null=True, blank=True
    )
    charged_credits = models.IntegerField(default=0)
    usage = models.JSONField(default=dict, blank=True)
    settled_by = models.CharField(max_length=32, blank=True, default="")
    transaction = models.ForeignKey(
        "app_users.AppUserTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["workspace", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.call_id} ({self.get_status_display()})"

    @property
    def invoice_id(self) -> str:
        return f"gooey_model_api_{self.call_id}"
