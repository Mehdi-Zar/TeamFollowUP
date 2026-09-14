"""Moral de l'equipe: trois niveaux, une date, un commentaire facultatif.

Trois niveaux et pas cinq: une echelle fine invite a la nuance, or ce qu'on
cherche ici est un signal, pas une note. La date accompagne le niveau parce qu'un
moral de mars affiche en septembre ment plus surement qu'une case vide.
"""
import sqlalchemy as sa
from alembic import op

revision = "0032_squad_mood"
down_revision = "0031_data_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("squads", sa.Column("mood", sa.String(length=10), nullable=True))
    op.add_column("squads", sa.Column("mood_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("squads", sa.Column("mood_comment", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("squads", "mood_comment")
    op.drop_column("squads", "mood_at")
    op.drop_column("squads", "mood")
