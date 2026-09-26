"""L'email d'un membre, cle du lien avec son compte.

Un membre ajoute depuis un ecran n'etait qu'un nom: rien ne le reliait au compte
de la personne, alors que ce lien decide qui valide ses conges et qui recoit les
rapports de la squad. L'email le porte desormais (voir app/memberlink.py).

Les membres deja relies a un compte recoivent l'email de ce compte, pour que le
lien se lise de la meme facon partout.
"""
import sqlalchemy as sa
from alembic import op

revision = "0036_member_email"
down_revision = "0035_otd_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("members", sa.Column("email", sa.String(length=255), nullable=True))
    op.create_index("ix_members_email", "members", ["email"])
    op.execute(
        "UPDATE members SET email = (SELECT lower(users.email) FROM users WHERE users.id = members.user_id) "
        "WHERE user_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_members_email", table_name="members")
    op.drop_column("members", "email")
