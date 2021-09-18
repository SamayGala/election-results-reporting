# pylint: disable=invalid-name
"""Initial
Revision ID: a13bc6d60456
Revises: 
Create Date: 2021-08-26 07:48:50.899848+00:00
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a13bc6d60456'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "file",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("contents", sa.Text(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.Column("processing_started_at", sa.DateTime(), nullable=True),
        sa.Column("processing_completed_at", sa.DateTime(), nullable=True),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("file_pkey")),
    )
    op.create_table(
        "organization",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("organization_pkey")),
    )
    op.create_table(
        "user",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("user_pkey")),
        sa.UniqueConstraint("email", name=op.f("user_email_key")),
        sa.UniqueConstraint("external_id", name=op.f("user_external_id_key")),
    )
    op.create_table(
        "election_administration",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("organization_id", sa.String(length=200), nullable=False),
        sa.Column("user_id", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("election_administration_organization_id_fkey"),
            ondelete="cascade",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("election_administration_user_id_fkey"),
            ondelete="cascade",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id", "user_id", name=op.f("election_administration_pkey")
        ),
    )
    op.create_table(
        "election",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=200), nullable=False),
        sa.Column("election_name", sa.String(length=200), nullable=False),
        sa.Column("polls_open_at", sa.DateTime(), nullable=False),
        sa.Column("polls_close_at", sa.DateTime(), nullable=False),
        sa.Column("polls_timezone", sa.String(length=4), nullable=False),
        sa.Column("certification_date", sa.DateTime(), nullable=False),
        sa.Column("organization_id", sa.String(length=200), nullable=False),
        sa.Column("jurisdictions_file_id", sa.String(length=200), nullable=False),
        sa.Column("definition_file_id", sa.String(length=200), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["jurisdictions_file_id"],
            ["file.id"],
            name=op.f("election_jurisdictions_file_id_fkey"),
            ondelete="set null",
        ),
        sa.ForeignKeyConstraint(
            ["definition_file_id"],
            ["file.id"],
            name=op.f("election_definition_file_id_fkey"),
            ondelete="set null",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("election_organization_id_fkey"),
            ondelete="cascade",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("election_pkey")),
        sa.UniqueConstraint(
            "organization_id",
            "election_name",
            name=op.f("election_organization_id_election_name_key"),
        ),
    )
    op.create_table(
        "jurisdiction",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=200), nullable=False),
        sa.Column("election_id", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["election_id"],
            ["election.id"],
            name=op.f("jurisdiction_election_id_fkey"),
            ondelete="cascade",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("jurisdiction_pkey")),
        sa.UniqueConstraint(
            "election_id", "name", name=op.f("jurisdiction_election_id_name_key")
        ),
    )
    op.create_table(
        "jurisdiction_administration",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.String(length=200), nullable=False),
        sa.Column("jurisdiction_id", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["jurisdiction_id"],
            ["jurisdiction.id"],
            name=op.f("jurisdiction_administration_jurisdiction_id_fkey"),
            ondelete="cascade",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("jurisdiction_administration_user_id_fkey"),
            ondelete="cascade",
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "jurisdiction_id", name=op.f("jurisdiction_administration_pkey")
        ),
    )


def downgrade():
    pass  # pragma: no cover
    # ### commands auto generated by Alembic - please adjust! ###
    # op.drop_table("jurisdiction_administration")
    # op.drop_table("jurisdiction")
    # op.drop_table("election")
    # op.drop_table("election_administration")
    # op.drop_table("user")
    # op.drop_table("organization")
    # op.drop_table("file")
    # ### end Alembic commands ###
