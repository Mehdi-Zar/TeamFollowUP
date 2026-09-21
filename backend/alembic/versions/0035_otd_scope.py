"""Deux portees d'engagement: celui du management, celui de la squad.

L'OTD etait un objet du tribe leader, et lui seul. Un squad leader qui prenait un
engagement date devant sa propre squad n'avait nulle part ou l'ecrire: il le
mettait dans un jalon, ou dans un message cle, c'est a dire dans un endroit d'ou
aucun rapport ne sait le relire comme un engagement.

La portee (``scope``) le dit donc explicitement. ``management`` est l'engagement
fixe par le haut, ecrit par le tribe leader ou un admin, et c'est ce que toutes
les lignes existantes deviennent. ``squad`` est celui que le squad leader prend
et gere lui-meme, sur une squad (``squad_id``) qu'il dirige.

Le lien vers les jalons est double. ``roadmap_items.otd_id`` reste le lien de
l'engagement management; ``squad_otd_id`` porte celui de la squad. Un seul lien
aurait oblige a choisir: le meme jalon sert en general les deux engagements, et
le dernier qui rattache aurait defait le travail de l'autre sans le lui dire.
"""
import sqlalchemy as sa
from alembic import op

revision = "0035_otd_scope"
down_revision = "0034_jalon_initiative"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default sur la colonne: les lignes existantes sont, par definition,
    # les engagements du management. Le defaut reste en base apres coup, pour que
    # l'insertion d'une ligne par un outil externe (import, script) reste valide.
    op.add_column("otds", sa.Column("scope", sa.String(length=12), nullable=False,
                                    server_default="management"))
    op.add_column("otds", sa.Column("squad_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_otds_squad", "otds", "squads", ["squad_id"], ["id"],
                          ondelete="CASCADE")
    op.create_index("ix_otds_squad_id", "otds", ["squad_id"])

    op.add_column("roadmap_items", sa.Column("squad_otd_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_roadmap_items_squad_otd", "roadmap_items", "otds",
                          ["squad_otd_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_roadmap_items_squad_otd_id", "roadmap_items", ["squad_otd_id"])


def downgrade() -> None:
    op.drop_index("ix_roadmap_items_squad_otd_id", table_name="roadmap_items")
    op.drop_constraint("fk_roadmap_items_squad_otd", "roadmap_items", type_="foreignkey")
    op.drop_column("roadmap_items", "squad_otd_id")

    # Les engagements de squad n'ont pas d'equivalent dans l'ancien schema: les
    # garder en les faisant passer pour des engagements du management serait pire
    # que de les retirer, puisqu'ils apparaitraient alors comme fixes par le haut.
    op.execute("DELETE FROM otds WHERE scope = 'squad'")
    op.drop_index("ix_otds_squad_id", table_name="otds")
    op.drop_constraint("fk_otds_squad", "otds", type_="foreignkey")
    op.drop_column("otds", "squad_id")
    op.drop_column("otds", "scope")
