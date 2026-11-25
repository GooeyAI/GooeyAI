from __future__ import annotations

import typing

from django.db import models
from django.template.defaultfilters import filesizeformat
from loguru import logger

from bots.custom_fields import CustomURLField

if typing.TYPE_CHECKING:
    from django.db.models import QuerySet
    from google.cloud.storage import Blob

    from app_users.models import AppUser


class FileMetadata(models.Model):
    name = models.TextField(default="", blank=True)
    etag = models.CharField(max_length=255, null=True)
    mime_type = models.CharField(max_length=255, default="", blank=True)
    total_bytes = models.PositiveIntegerField(default=0, blank=True)

    export_links: dict[str, str] | None = None
    ref_data: dict | None = None

    def __str__(self):
        ret = f"{self.name or 'Unnamed'} - {self.mime_type}"
        if self.total_bytes:
            ret += f" - {filesizeformat(self.total_bytes)}"
        if self.etag:
            ret += f" - {self.etag}"
        return ret

    def __eq__(self, other):
        ret = bool(
            isinstance(other, FileMetadata)
            # avoid null comparisions -- when metadata is not available and hence not comparable
            and (self.etag or other.etag or self.total_bytes or other.total_bytes)
            and self.astuple() == other.astuple()
        )
        logger.debug(f"checking: `{self}` == `{other}` ({ret})")
        return ret

    def astuple(self) -> tuple:
        return self.name, self.etag, self.mime_type, self.total_bytes

    class Meta:
        indexes = [
            models.Index(fields=["name", "etag", "mime_type", "total_bytes"]),
        ]


class UploadedFileManager(models.Manager):
    def from_gcs_blob(self, blob: Blob) -> QuerySet[UploadedFile]:
        return self.filter(bucket_name=blob.bucket.name, object_name=blob.name)


class UploadedFile(models.Model):
    metadata = models.ForeignKey(
        "files.FileMetadata",
        on_delete=models.CASCADE,
        related_name="uploaded_files",
    )
    f_url = CustomURLField(unique=True, verbose_name="File URL")
    bucket_name = models.CharField(max_length=255)
    object_name = models.TextField()
    saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.SET_NULL,
        related_name="uploaded_files",
        null=True,
        blank=True,
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.SET_NULL,
        related_name="uploaded_files",
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,
        related_name="uploaded_files",
        null=True,
        blank=True,
    )
    is_user_uploaded = models.BooleanField(default=False)
    is_uploading = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    objects = UploadedFileManager()

    def __str__(self):
        name = self.metadata.name or "Unnamed"
        if self.metadata.total_bytes:
            return f"{name} - {filesizeformat(self.metadata.total_bytes)}"
        return name

    class Meta:
        indexes = [
            models.Index(
                fields=["workspace", "created_at"],
                name="files_uploa_workspa_3d4b4a_idx",
            ),
            models.Index(
                fields=["user", "created_at"],
                name="files_uploa_user_id_7bdbf8_idx",
            ),
            models.Index(
                fields=["created_at"],
                name="files_uploa_created_5e3e16_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["bucket_name", "object_name"],
                name="uploadedfile_bucket_object_unique",
            ),
        ]


def access_level_choices():
    # Called while the models below are defined, so it sits above them. Imported lazily
    # because bots.models imports app_users.models, which imports this module.
    from bots.models.workflow import WorkflowAccessLevel

    return WorkflowAccessLevel.choices


class Artifact(models.Model):
    """A website made by functions: a top-level folder of the workspace files that holds an
    `index.html`. The folder name is its name and its address, `/<handle>/<folder>/`.

    Works like an agent. Every Ask Gooey edit makes a draft with its own link (as a run
    does), and the live page changes only when someone presses Update, which adds a version
    pointing at that draft (as a published run version points at a run). `<folder>/` holds
    the live version's files.
    """

    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        related_name="artifacts",
    )
    folder = models.TextField()
    created_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,
        related_name="artifacts",
        null=True,
        blank=True,
    )
    # Private (creator only) / View only / Editable, as for workflows
    workspace_access = models.IntegerField(
        choices=access_level_choices,
        default=2,  # WorkflowAccessLevel.FIND_AND_VIEW
    )
    # "View Only" here = anyone with the link, signed in or not
    public_access = models.IntegerField(
        choices=access_level_choices,
        default=1,  # WorkflowAccessLevel.VIEW_ONLY
    )
    # the version everyone sees, which matches `<folder>/`
    live_version = models.ForeignKey(
        "files.ArtifactVersion",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.folder

    def can_user_view(self, user: AppUser | None) -> bool:
        """
        Public: anyone with the link. Private: the creator. View only / Editable: every
        member. Gooey staff see everything.
        """
        from bots.models.workflow import WorkflowAccessLevel

        if self.public_access == WorkflowAccessLevel.FIND_AND_VIEW:
            return True
        if not user or user.is_anonymous:
            return False
        if user.is_admin():
            return True
        if not self.is_member(user):
            return False
        return (
            self.workspace_access != WorkflowAccessLevel.VIEW_ONLY
            or self.created_by_id == user.id
        )

    def can_user_edit(self, user: AppUser | None) -> bool:
        """Who may Update the live page: managers, plus members when Editable."""
        from bots.models.workflow import WorkflowAccessLevel

        if self.can_user_manage(user):
            return True
        if not user or user.is_anonymous:
            return False
        return self.workspace_access == WorkflowAccessLevel.EDIT and self.is_member(
            user
        )

    def can_user_manage(self, user: AppUser | None) -> bool:
        """
        Who may rename, delete and change sharing: the creator and staff, plus workspace
        admins and owners unless it's private.
        """
        from bots.models.workflow import WorkflowAccessLevel

        if not user or user.is_anonymous:
            return False
        if user.is_admin():
            return True
        if not self.is_member(user):
            return False
        if self.created_by_id == user.id:
            return True
        return (
            self.workspace_access != WorkflowAccessLevel.VIEW_ONLY
            and self.workspace.get_admins().filter(id=user.id).exists()
        )

    def is_member(self, user: AppUser | None) -> bool:
        if not user or user.is_anonymous:
            return False
        return self.workspace_id in {w.id for w in user.cached_workspaces}

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "folder"],
                name="artifact_workspace_folder_unique",
            ),
        ]


class ArtifactDraft(models.Model):
    """One Ask Gooey message's result, like an agent's saved run: a copy of the folder at
    `.drafts/<folder>/<draft_id>/` with its own link, `/<handle>/<folder>/?draft=<draft_id>`.
    Ask Gooey edits it while that message runs; after that it stays as it is."""

    artifact = models.ForeignKey(
        "files.Artifact",
        on_delete=models.CASCADE,
        related_name="drafts",
    )
    draft_id = models.TextField(unique=True)
    created_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    # the draft the edit started from
    based_on = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    # the Ask Gooey message whose edit made it, if any
    builder_saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.artifact} draft {self.draft_id}"


class ArtifactVersion(models.Model):
    """A press of Update, like a published run version: the draft that went live."""

    artifact = models.ForeignKey(
        "files.Artifact",
        on_delete=models.CASCADE,
        related_name="versions",
    )
    number = models.PositiveIntegerField()
    draft = models.ForeignKey(
        "files.ArtifactDraft",
        on_delete=models.CASCADE,
        related_name="versions",
    )
    created_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    # the change notes typed in the Update dialog
    note = models.TextField(default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.artifact} v{self.number}"

    class Meta:
        ordering = ["-number"]
        constraints = [
            models.UniqueConstraint(
                fields=["artifact", "number"],
                name="artifactversion_artifact_number_unique",
            ),
        ]


class ArtifactChat(models.Model):
    """Each member's Ask Gooey conversation beside an artifact. Every message in it makes a
    draft, which Ask Gooey edits."""

    artifact = models.ForeignKey(
        "files.Artifact",
        on_delete=models.CASCADE,
        related_name="chats",
    )
    user = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.CASCADE,
        related_name="+",
    )
    builder_saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["artifact", "user"],
                name="artifactchat_artifact_user_unique",
            ),
        ]
