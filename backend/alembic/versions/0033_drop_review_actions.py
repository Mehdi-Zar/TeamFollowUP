"""Retirer les actions de revue.

Elles avaient une table, un routeur, un ecran et des tests, et ne servaient plus.
Sorties du parcours de reporting parce qu'une decision de comite ne se prend pas au
rythme hebdomadaire, puis jugees inutiles sur la page d'une squad.

La retirer a moitie aurait ete pire que de la garder: une route sans ecran ment sur
ce que l'application sait faire. La table part donc avec le reste.

Le retour en arriere recree la table vide. Il ne rend pas les lignes: une migration
descendante retablit une forme, jamais un contenu. Ce qui protege le contenu est la
sauvegarde prise avant la mise a jour (docs/19), pas ce fichier.
"""
import sqlalchemy as sa
from alembic import op

revision = "0033_drop_review_actions"
down_revision = "0032_squad_mood"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("review_actions")


def downgrade() -> None:
    op.create_table(
        "review_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("squad_id", sa.Integer(), sa.ForeignKey("squads.id"), nullable=False, index=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
