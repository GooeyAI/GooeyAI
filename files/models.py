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

    Storage, under `workspace_files_prefix(workspace_id)`:
    - `<folder>/`: the working copy until the first publish, then a copy of the live version
    - `.drafts/<user_id>/<folder>/`: one draft per editor
    - `.versions/<folder>/<n>/`: a snapshot per version; `live_version` is what the page shows
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
        Before the first publish only editors see it. After: Public = anyone with the link;
        Private = the creator; View only / Editable = every member; staff see everything.
        """
        from bots.models.workflow import WorkflowAccessLevel

        if not self.live_version_id:
            return self.can_user_edit(user)
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
        """Who may keep a draft and propose versions: managers, plus members when Editable."""
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
        Who may publish, make a version live and change sharing: the creator and staff, plus
        workspace admins and owners unless it's private.
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


class ArtifactVersion(models.Model):
    class Status(models.IntegerChoices):
        # made by an editor who can't publish; waits for a manager to make it live
        PROPOSED = 1
        PUBLISHED = 2

    artifact = models.ForeignKey(
        "files.Artifact",
        on_delete=models.CASCADE,
        related_name="versions",
    )
    number = models.PositiveIntegerField()
    status = models.IntegerField(choices=Status.choices)
    created_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    # the version the draft started from, for "the live page changed since"
    base_number = models.PositiveIntegerField(null=True, blank=True)
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


class ArtifactDraft(models.Model):
    """An editor's working copy, at `.drafts/<user_id>/<folder>/`."""

    artifact = models.ForeignKey(
        "files.Artifact",
        on_delete=models.CASCADE,
        related_name="drafts",
    )
    user = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.CASCADE,
        related_name="+",
    )
    # None when it started from the working copy, before any version existed
    base_number = models.PositiveIntegerField(null=True, blank=True)
    # the Ask Gooey conversation editing this draft
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
                name="artifactdraft_artifact_user_unique",
            ),
        ]
