import enum
from typing import Type, TypeVar, cast as typing_cast
from datetime import datetime as dt, timezone
from werkzeug.exceptions import NotFound
from sqlalchemy import *  # pylint: disable=wildcard-import
import sqlalchemy
from sqlalchemy.orm import (
    relationship,
    backref,
    validates,
    deferred as sa_deferred,
)
from sqlalchemy.types import TypeDecorator
from .database import Base  # pylint: disable=cyclic-import

C = TypeVar("C")  # pylint: disable=invalid-name

# Workaround to make sqlalchemy.orm.deferred have the right type
def deferred(col: C) -> C:
    return typing_cast(C, sa_deferred(col))


# Define a custom function to sort mixed text/number strings
# From https://stackoverflow.com/a/20667107/1472662
# You can call this function using func.human_sort
sqlalchemy.event.listen(
    Base.metadata,
    "after_create",
    DDL(
        """
            BEGIN;
            SELECT pg_advisory_xact_lock(2142616474639426746); -- lock so that tests can run this concurrently
            CREATE OR REPLACE FUNCTION human_sort(text)
            RETURNS text[] AS
            $BODY$
            /* Split the input text into contiguous chunks where no numbers appear,
                and contiguous chunks of only numbers. For the numbers, add leading
                zeros to 20 digits, so we can use one text array, but sort the
                numbers as if they were big integers.
                For example, human_sort('Run 12 Miles') gives
                        {'Run ', '00000000000000000012', ' Miles'}
            */
            select array_agg(
                case
                when a.match_array[1]::text is not null
                    then a.match_array[1]::text
                else lpad(a.match_array[2]::text, 20::int, '0'::text)::text
                end::text)
                from (
                select regexp_matches(
                    case when $1 = '' then null else $1 end, E'(\\\\D+)|(\\\\d+)', 'g'
                ) AS match_array
                ) AS a
            $BODY$
            LANGUAGE sql IMMUTABLE;
            COMMIT;
        """
    ),
)


class UTCDateTime(TypeDecorator):  # pylint: disable=abstract-method
    # Store with no timezone
    impl = DateTime

    # Ensure UTC timezone on write
    def process_bind_param(self, value, dialect):
        if value:
            assert (
                value.tzinfo == timezone.utc
            ), "All datetimes must have UTC timezone - use datetime.now(timezone.utc)"
        return value

    # Repopulate UTC timezone on read
    def process_result_value(self, value, dialect):
        return value and value.replace(tzinfo=timezone.utc)


class BaseModel(Base):
    __abstract__ = True
    created_at = Column(
        UTCDateTime, default=lambda: dt.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        UTCDateTime,
        default=lambda: dt.now(timezone.utc),
        onupdate=lambda: dt.now(timezone.utc),
        nullable=False,
    )


# on-delete-cascade is done in SQLAlchemy like this:
# https://stackoverflow.com/questions/5033547/sqlalchemy-cascade-delete

class State(BaseModel):
    id = Column(String(200), primary_key=True)
    name = Column(String(200), nullable=False, unique=True)

    jurisdictions = relationship(
        "Jurisdiction",
        back_populates="state",
        uselist=True,
        passive_deletes=True,
        order_by="Jurisdiction.name",
    )


class Organization(BaseModel):
    id = Column(String(200), primary_key=True)
    name = Column(String(200), nullable=False, unique=True)

    elections = relationship(
        "Election",
        back_populates="organization",
        uselist=True,
        passive_deletes=True,
        order_by="Election.name",
    )


# these are typically counties
class Jurisdiction(BaseModel):
    id = Column(String(200), primary_key=True)
    name = Column(String(200), nullable=False)

    state_id = Column(
        String(200),
        ForeignKey("state.id", ondelete="cascade"),
        nullable=False
    )
    state = relationship("State", back_populates="jurisdictions")

    # Precincts in that jurisdiction
    precincts = relationship(
        "Precinct",
        back_populates="jurisdiction",
        uselist=True,
        passive_deletes=True,
        order_by="Precinct.name",
    )
    # Election in that jurisdiction
    elections = relationship(
        "Election",
        secondary="election_jurisdiction",
        uselist=True,
        passive_deletes=True,
    )

    __table_args__ = (UniqueConstraint("state_id", "name"),)


class Precinct(BaseModel):
    id = Column(String(200), primary_key=True)
    name = Column(String(200), nullable=False)
    definitions_file_id = Column(String(200), nullable=False)

    jurisdiction_id = Column(
        String(200),
        ForeignKey("jurisdiction.id", ondelete="cascade"),
        nullable=False
    )
    jurisdiction = relationship("Jurisdiction", back_populates="precincts")

    __table_args__ = (UniqueConstraint("jurisdiction_id", "name"),)


# Election is a slight misnomer - this model represents an Election.
class Election(BaseModel):
    id = Column(String(200), primary_key=True)

    name = Column(String(200), nullable=False)
    polls_open_at = Column(UTCDateTime, nullable=False)
    polls_close_at = Column(UTCDateTime, nullable=False)
    polls_timezone = Column(String(5), nullable=False)
    certification_date = Column(UTCDateTime, nullable=False)

    # Who does this election belong to?
    organization_id = Column(
        String(200),
        ForeignKey("organization.id", ondelete="cascade"),
        nullable=False
    )
    organization = relationship("Organization", back_populates="elections")

    # The jurisdictions file contains a list of jurisdictions
    # and emails for the admins of each jurisdiction.
    # We use this to create Jurisdictions and JAs.
    jurisdictions_file_id = Column(
        String(200), ForeignKey("file.id", ondelete="set null")
    )
    jurisdictions_file = relationship(
        "File",
        foreign_keys=[jurisdictions_file_id],
        single_parent=True,
        cascade="all, delete-orphan",
    )

    # The definition file contains election related data
    definition_file_id = Column(
        String(200), ForeignKey("file.id", ondelete="set null")
    )
    definition_file = relationship(
        "File",
        foreign_keys=[definition_file_id],
        single_parent=True,
        cascade="all, delete-orphan",
    )

    # Contests in the election
    contests = relationship(
        "Contest",
        back_populates="election",
        uselist=True,
        passive_deletes=True,
        order_by="Contest.name",
    )
    # Jurisdictions in the election
    jurisdictions = relationship(
        "Jurisdiction",
        secondary="election_jurisdiction",
        uselist=True,
        order_by="Jurisdiction.name",
        passive_deletes=True,
    )

    # When a user deletes an election, we keep it in the database just in case
    # they change their mind, but flag it so that we can restrict access
    deleted_at = Column(UTCDateTime)

    @validates('polls_timezone')
    def convert_upper(self, _key, polls_timezone):
        return polls_timezone.upper()

    __table_args__ = (UniqueConstraint("organization_id", "name"),)


class ElectionJurisdiction(Base):
    election_id = Column(
        String(200),
        ForeignKey("election.id", ondelete="cascade"),
        nullable=False,
    )
    jurisdiction_id = Column(
        String(200),
        ForeignKey("jurisdiction.id", ondelete="cascade"),
        nullable=False,
    )
    __table_args__ = (PrimaryKeyConstraint("election_id", "jurisdiction_id"),)


class Contest (BaseModel):
    id = Column(String(200), primary_key=True)
    name = Column(String(200), nullable=False)
    type = Column(String(200), nullable=False)
    seats = Column(String(200), nullable=False)
    allow_write_ins = Column(Boolean, nullable=False)
    definitions_file_id = Column(String(200), nullable=False)

    election_id = Column(
        String(200),
        ForeignKey("election.id", ondelete="cascade"),
        nullable=False
    )
    election = relationship("Election", back_populates="contests")

    # The candidates participating in the contest
    candidates = relationship(
        "Candidate",
        back_populates="contest",
        uselist=True,
        passive_deletes=True,
        order_by="Candidate.name",
    )

    __table_args__ = (UniqueConstraint("election_id", "name"),)


class Candidate (BaseModel):
    id = Column(String(200), primary_key=True)
    name = Column(String(200), nullable=False)
    definitions_file_id = Column(String(200), nullable=False)

    contest_id = Column(
        String(200),
        ForeignKey("contest.id", ondelete="cascade"),
        nullable=False
    )
    contest = relationship("Contest", back_populates="candidates")

    __table_args__ = (UniqueConstraint("contest_id", "name"),)


class ElectionResultSource(str, enum.Enum):
    FILE = "File"
    DATA_ENTRY = "Data Entry"

class ElectionResult(BaseModel):
    id = Column(String(200), primary_key=True)
    source = Column(Enum(ElectionResultSource), nullable=False)
    #Precinct to which results belong
    precinct_id = Column(
        String(200),
        ForeignKey("precinct.id", ondelete="cascade"),
        nullable=False
    )
    precinct = relationship("Precinct")
    # Candidate whose result is to be stored
    candidate_id = Column(
        String(200),
        ForeignKey("candidate.id", ondelete="cascade"),
        nullable=False
    )
    candidate = relationship("Candidate")
    # number of votes for each candidate (including write-ins)
    num_votes = Column(Integer, nullable=False)
    # When a user deletes an election result, we keep it in the database just in case
    # they change their mind, but flag it so that we can restrict access
    deleted_at = Column(UTCDateTime)

    __table_args__ = (UniqueConstraint("precinct_id", "candidate_id"),)


class User(BaseModel):
    id = Column(String(200), primary_key=True)
    email = Column(String(200), unique=True, nullable=False)
    external_id = Column(String(200), unique=True)

    organizations = relationship(
        "Organization",
        secondary="election_administration",
        uselist=True
    )
    jurisdictions = relationship(
        "Jurisdiction",
        secondary="jurisdiction_administration",
        uselist=True
    )

    @validates("email")
    def lowercase_email(self, _key, email):
        return email.lower()


class ElectionAdministration(BaseModel):
    organization_id = Column(
        String(200),
        ForeignKey("organization.id", ondelete="cascade"),
        nullable=False
    )
    user_id = Column(
        String(200),
        ForeignKey("user.id", ondelete="cascade"),
        nullable=False
    )

    organization = relationship(
        "Organization",
        backref=backref("election_administrations", cascade="all, delete-orphan")
    )
    user = relationship(
        "User",
        backref=backref("election_administrations", cascade="all, delete-orphan")
    )

    __table_args__ = (PrimaryKeyConstraint("organization_id", "user_id"),)


class JurisdictionAdministration(BaseModel):
    user_id = Column(
        String(200),
        ForeignKey("user.id", ondelete="cascade"),
        nullable=False
    )
    jurisdiction_id = Column(
        String(200),
        ForeignKey("jurisdiction.id", ondelete="cascade"),
        nullable=False,
    )

    jurisdiction = relationship(
        "Jurisdiction",
        backref=backref("jurisdiction_administrations", cascade="all, delete-orphan"),
    )
    user = relationship(
        "User",
        backref=backref("jurisdiction_administrations", cascade="all, delete-orphan"),
    )

    __table_args__ = (PrimaryKeyConstraint("user_id", "jurisdiction_id"),)


class File(BaseModel):
    id = Column(String(200), primary_key=True)
    name = Column(String(250), nullable=False)
    contents = deferred(Column(Text, nullable=False))
    uploaded_at = Column(
        UTCDateTime,
        default=lambda: dt.now(timezone.utc),
        nullable=False
    )

    # Metadata for processing files.
    processing_started_at = Column(UTCDateTime)
    processing_completed_at = Column(UTCDateTime)
    processing_error = Column(Text)


class ActivityLogRecord(Base):
    id = Column(String(200), primary_key=True)
    timestamp = Column(UTCDateTime, nullable=False)
    organization_id = Column(
        String(200),
        ForeignKey("organization.id", ondelete="cascade"),
        nullable=False
    )
    activity_name = Column(String(200), nullable=False)
    info = Column(JSON, nullable=False)


class ProcessingStatus(str, enum.Enum):
    READY_TO_PROCESS = "READY_TO_PROCESS"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    ERRORED = "ERRORED"


def get_or_404(model: Type[Base], primary_key: str):
    instance = model.query.get(primary_key)
    if instance:
        return instance
    raise NotFound(f"{model.__class__.__name__} {primary_key} not found")
