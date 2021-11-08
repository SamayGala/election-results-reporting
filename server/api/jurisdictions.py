
import uuid
import logging
from typing import Tuple, List
from flask import jsonify, request
from werkzeug.exceptions import BadRequest, Conflict

from . import api
from ..models import *  # pylint: disable=wildcard-import
from ..database import db_session
from ..auth import restrict_access, UserType

from ..util.jsonschema import JSONDict, validate
from ..util.process_file import serialize_file, serialize_file_processing, process_file
from ..util.csv_parse import decode_csv_file, parse_csv, CSVValueType, CSVColumnType

logger = logging.getLogger("elrep")


JURISDICTION_NAME = "Jurisdiction"
ADMIN_EMAIL = "Admin Email"

JURISDICTIONS_COLUMNS = [
    CSVColumnType("Jurisdiction", CSVValueType.TEXT, unique=True),
    CSVColumnType("Admin Email", CSVValueType.EMAIL, unique=True),
]

def process_jurisdictions_file(session, election: Election, file: File) -> None:
    def process():
        jurisdictions_csv = parse_csv(
            election.jurisdictions_file.contents, JURISDICTIONS_COLUMNS
        )
        bulk_update_jurisdictions(
            session,
            election,
            [(row[JURISDICTION_NAME], row[ADMIN_EMAIL]) for row in jurisdictions_csv],
        )

    process_file(session, file, process)


def bulk_update_jurisdictions(
    session, election: Election, name_and_admin_email_pairs: List[Tuple[str, str]]
) -> List[JurisdictionAdministration]:
    """
    Updates the jurisdictions for an election all at once. Requires a SQLAlchemy session to use,
    and uses a nested transaction to ensure the changes made are atomic. Depending on your
    session configuration, you may need to explicitly call `commit()` on the session to flush
    changes to the database.
    """
    with session.begin_nested():
        # Clear existing admins.
        session.query(JurisdictionAdministration).filter(
            JurisdictionAdministration.jurisdiction_id.in_(
                ElectionJurisdiction.query.filter_by(election_id=election.id)
                .with_entities(ElectionJurisdiction.jurisdiction_id)
                .subquery()
            )
        ).delete(synchronize_session="fetch")
        new_admins: List[JurisdictionAdministration] = []

        for (name, email) in name_and_admin_email_pairs:
            # Find or create the user for this jurisdiction.
            user = session.query(User).filter_by(email=email.lower()).one_or_none()

            if not user:
                user = User(id=str(uuid.uuid4()), email=email)
                session.add(user)

            # Find the jurisdiction by name.
            # Creating Jurisdiction is not allowed here, since they are seeded/created in the start
            jurisdiction = Jurisdiction.query\
            .filter_by(name=name)\
            .join(ElectionJurisdiction, and_(ElectionJurisdiction.jurisdiction_id == Jurisdiction.id, ElectionJurisdiction.election_id == election.id))\
            .one_or_none()

            if not jurisdiction:
                raise BadRequest("Invalid Jurisdiction")

            # Link the user to the jurisdiction as an admin.
            admin = JurisdictionAdministration(jurisdiction=jurisdiction, user=user)
            session.add(admin)
            new_admins.append(admin)

        return new_admins


ELECTION_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "totalBallotsCast": {"type": "string"},
        "precinct": {"type": "string"},
        "source": {"type": "string", "enum": [source.value for source in ElectionResultSource]},
        "contests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "candidates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "numVotes": {"type": "string"}
                            },
                            "required": ["id", "numVotes"],
                            "additionalProperties": True,
                        },
                    },
                },
                "required": ["id", "candidates"],
                "additionalProperties": True,
            },
        },
    },
    "required": ["source", "precinct", "contests"],
    "additionalProperties": False,
}

def validate_election_result(election_result: JSONDict):
    validate(election_result, ELECTION_RESULT_SCHEMA)
    record_found = False
    for itr_contest in election_result["contests"]:
        if ElectionResult.query.filter_by(
            precinct_id=election_result["precinct"],
            candidate_id=itr_contest["candidates"][0]["id"]
        ).first():
            record_found = True
    if record_found:
        raise Conflict("Results for this precinct are already uploaded")


@api.route("/election/<election_id>/jurisdiction/file", methods=["GET"])
@restrict_access([UserType.ELECTION_ADMIN, UserType.JURISDICTION_ADMIN])
def get_jurisdictions_file(election: Election):
    return jsonify(
        file=serialize_file(election.jurisdictions_file),
        processing=serialize_file_processing(election.jurisdictions_file),
    )

@api.route("/election/<election_id>/jurisdiction/file", methods=["PUT"])
@restrict_access([UserType.ELECTION_ADMIN])
def update_jurisdictions_file(election: Election):
    if "jurisdictions" not in request.files:
        raise BadRequest("Missing required file parameter 'jurisdictions'")

    jurisdictions_file = request.files["jurisdictions"]
    election.jurisdictions_file = File(
        id=str(uuid.uuid4()),
        name=jurisdictions_file.filename,
        contents=decode_csv_file(jurisdictions_file),
    )
    db_session.commit()
    return jsonify(status="ok")


@api.route("/election/<election_id>/jurisdiction/<jurisdiction_id>/results", methods=["GET"])
@restrict_access([UserType.JURISDICTION_ADMIN])
def check_election_result_status(election: Election, jurisdiction: Jurisdiction):
    records_status = {
        "uploaded": 0,
        "notUploaded": 0
    }
    for itr_precinct in jurisdiction.precincts:
        record_found = False
        for itr_contest in election.contests:
            if ElectionResult.query.filter_by(precinct_id=itr_precinct.id, candidate_id=itr_contest.candidates[0].id).one_or_none():
                record_found = True
        if record_found:
            records_status["uploaded"] += 1
        else:
            records_status["notUploaded"] += 1

    if records_status["notUploaded"]:
        return jsonify(status="not-uploaded", stats=records_status)
    return jsonify(status="uploaded")

@api.route("/election/<election_id>/jurisdiction/<jurisdiction_id>/results", methods=["POST"])
@restrict_access([UserType.JURISDICTION_ADMIN])
def upload_election_results(election: Election, jurisdiction: Jurisdiction):
    request_json = request.get_json()
    validate_election_result(request_json)
    if len(request_json['contests']) != len(list(set(item for item in [itr_contest['id'] for itr_contest in request_json['contests']]))):
        raise Conflict(f"Contests should be unique for ({election.name} - {jurisdiction.name}) results")

    for itr_contest in request_json['contests']:
        for itr_candidate in itr_contest['candidates']:
            election_result = ElectionResult(
                id=str(uuid.uuid4()),
                source=request_json['source'],
                precinct_id=request_json['precinct'],
                candidate_id=itr_candidate['id'],
                num_votes=itr_candidate['numVotes']
            )
            db_session.add(election_result)
    db_session.commit()
    return jsonify(status="ok")
