"""Un jalon designe son initiative, sans passer par un objectif.

La frise des exports fait une ligne par initiative et y range les jalons qui la
servent. Le chemin passait par l'objectif annuel (jalon -> objectif ->
initiative), or aucun ecran ne posait jamais le second maillon: en pratique
chaque slide affichait des lignes d'initiative vides et une ligne anonyme portant
tous les jalons.

L'objectif portait donc deux roles a la fois: etre un objectif qu'on suit, dont
la synthese compte les rouges, et servir de tuyau. Le second lui est retire. Le
premier maillon (jalon -> objectif) reste: il dit a quel objectif un jalon
repond, ce qui n'est pas la meme question que « quelle initiative sert-il ».

La reprise des donnees suit l'ancien chemin tant qu'il existe: un jalon dont
l'objectif servait une initiative pointe desormais dessus directement.
"""
import sqlalchemy as sa
from alembic import op

revision = "0034_jalon_initiative"
down_revision = "0033_drop_review_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("roadmap_items", sa.Column("initiative_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_roadmap_items_initiative", "roadmap_items", "initiatives",
                          ["initiative_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_roadmap_items_initiative_id", "roadmap_items", ["initiative_id"])
    op.execute("""
        UPDATE roadmap_items
           SET initiative_id = (SELECT o.initiative_id
                                  FROM objectives o
                                 WHERE o.id = roadmap_items.objective_id)
         WHERE objective_id IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_index("ix_roadmap_items_initiative_id", table_name="roadmap_items")
    op.drop_constraint("fk_roadmap_items_initiative", "roadmap_items", type_="foreignkey")
    op.drop_column("roadmap_items", "initiative_id")
