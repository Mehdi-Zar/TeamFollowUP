"""Studio des exports: themes, files, templates and their versions, assignments.

The single PowerPoint template of Administration > Import stays where it is (it is
the master of the Standard theme); everything the Studio adds lives in its own
tables, so a document without any assignment renders exactly as before.
"""
import sqlalchemy as sa
from alembic import op

revision = "0043_export_studio"
down_revision = "0042_user_scim_external_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime", sa.String(length=100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("tribe_id", sa.Integer(), sa.ForeignKey("tribes.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_export_assets_tribe_id", "export_assets", ["tribe_id"])
    op.create_table(
        "export_themes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("master_asset_id", sa.Integer(), sa.ForeignKey("export_assets.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("tribe_id", sa.Integer(), sa.ForeignKey("tribes.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_export_themes_tribe_id", "export_themes", ["tribe_id"])
    op.create_table(
        "export_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doc_kind", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("scope_type", sa.String(length=10), nullable=False, server_default="global"),
        sa.Column("scope_id", sa.Integer(), nullable=True),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("export_templates.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("mode", sa.String(length=10), nullable=False, server_default="root"),
        sa.Column("system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("shared", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("draft", sa.JSON(), nullable=False),
        sa.Column("draft_locks", sa.JSON(), nullable=False),
        sa.Column("published_version_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_export_templates_doc_kind", "export_templates", ["doc_kind"])
    op.create_table(
        "export_template_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("export_templates.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("locks", sa.JSON(), nullable=False),
        sa.Column("comment", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("template_id", "number", name="uq_export_template_version"),
    )
    op.create_index("ix_export_template_versions_template_id", "export_template_versions", ["template_id"])
    op.create_table(
        "export_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doc_kind", sa.String(length=20), nullable=False),
        sa.Column("scope_key", sa.String(length=32), nullable=False),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("export_templates.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("doc_kind", "scope_key", name="uq_export_assignment"),
    )


def downgrade() -> None:
    op.drop_table("export_assignments")
    op.drop_index("ix_export_template_versions_template_id", table_name="export_template_versions")
    op.drop_table("export_template_versions")
    op.drop_index("ix_export_templates_doc_kind", table_name="export_templates")
    op.drop_table("export_templates")
    op.drop_index("ix_export_themes_tribe_id", table_name="export_themes")
    op.drop_table("export_themes")
    op.drop_index("ix_export_assets_tribe_id", table_name="export_assets")
    op.drop_table("export_assets")
